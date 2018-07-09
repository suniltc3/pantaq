from odoo import api, fields, models, _, SUPERUSER_ID
from lxml import etree
from odoo.exceptions import Warning
from odoo.addons import decimal_precision as dp


MAGIC_COLUMNS = ('id', 'create_uid', 'create_date', 'write_uid', 'write_date')

class PurchaseOrder(models.Model):
    _inherit = ['purchase.order']

    @api.model
    def fields_view_get(self, view_id=None, view_type=False, toolbar=False, submenu=False):

        def get_view_id(name):
            view = self.env['ir.ui.view'].search([('name', '=', name)], limit=1)
            if not view:
                return False
            return view.id

        context = dict(self._context)
        po_type = context.get('po_type', 'purchase')

        if view_type == 'form' and po_type == 'rfq':
            view_id = get_view_id('view_pq_rfq_form')

        if view_type == 'tree' and po_type == 'rfq':
            view_id = get_view_id('view_pq_rfq_tree')

        return super(PurchaseOrder, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)


    @api.depends('order_line.price_total', 'order_line.rfq_status')
    def _amount_all(self):

        context = dict(self._context)

        for order in self:
            amount_untaxed = amount_tax = 0.0

            for line in order.order_line:
                # In RFQ: consider only the approved lines
                if line.rfq_status != 'approved' and (order.po_type == 'rfq' or context.get('po_type','') == 'rfq'):
                    continue
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax

            order.update({
                'amount_untaxed': order.currency_id.round(amount_untaxed),
                'amount_tax': order.currency_id.round(amount_tax),
                'amount_total': amount_untaxed + amount_tax,
            })

    # Overridden:
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', track_visibility='always')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
        ('qtn_received', 'Response Received'),
        ('rfq_revised', 'RFQ Revised')
        ], string='Status', readonly=True, index=True, copy=False, default='draft', track_visibility='onchange')


    # New:
    po_type = fields.Selection([('rfq', 'RFQ'),('purchase', 'Purchase Order')], string='Order Type', default='purchase')
    remarks = fields.Text(string="Remarks")
    lead_id = fields.Many2one('crm.lead', string='Enquiry', index=True)
    backorder_id = fields.Many2one('purchase.order', string='BackOrder', index=True, help="Original RFQ mapped against each revised RFQs")

    irattachment_ids = fields.One2many('ir.attachment', 'res_id', string='Attachments',
        domain=lambda self: [('res_model', '=', self._name)])



    @api.multi
    @api.depends('name', 'partner_ref')
    def name_get(self):
        result = []
        for po in self:
            name = po.name
            if po.partner_ref:
                name += ' ('+po.partner_ref+')'
            # if po.amount_total:
            #     name += ': ' + formatLang(self.env, po.amount_total, currency_obj=po.currency_id)
            result.append((po.id, name))
        return result

    @api.model
    def _prepare_IntQuotation(self, rfq):
        """ Prepare the dict of values to create the new Internal Order from the RFQ.
        """
        values = {}

        for field in ['currency_id', 'company_id', 'lead_id']:
            if rfq._fields[field].type == 'many2one':
                values[field] = rfq[field].id
            else:
                values[field] = rfq[field] or False

        values.update({
            'name' : 'New',
            # 'note' : self.notes,
            'partner_id': self.lead_id.partner_id.id
        })

        return values


    @api.multi
    def button_create_InternalQtn(self):
        """
            Creates Internal Quotation for the Approved Lines
        """
        context = dict(self._context)
        cache = {}
        IntOrds = []

        CallBy = context.get('callby', '')
        selectedLns = context.get('selectedRfqLines', [])

        intord_obj = self.env['internal.order']

        for case in self:
            io = False
            approvedLines = []
            EnquiryRec = case.lead_id
            EnqLnNew = {}

            for rol in case.order_line:
                if CallBy == 'rfqProd' and rol.id not in selectedLns:
                    continue
                elif rol.rfq_status != 'approved':
                    continue

                approvedLines.append(rol.id)
                EnqLnNew.update({rol.enqline_id.id: rol.product_id.name})

            if not approvedLines:
                raise Warning(_("Please approve a product to proceed !!"))

            domain = (
                    ('state', '=', 'draft'),
                    ('lead_id', '=', EnquiryRec.id),
                    )

            if domain in cache:
                io = cache[domain]
            else:
                io = intord_obj.search([dom for dom in domain], order='id desc', limit=1)
                io = io[0] if io else False
                cache[domain] = io

            # iqRevise = False
            if not io:
                # Check: IQ Revision:
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                domain = (
                        ('state', '=', 'submit'),
                        ('lead_id', '=', EnquiryRec.id),
                        )

                io = intord_obj.search([dom for dom in domain], order='id desc', limit=1)
                if io:
                    io = io[0]
                    iqRevise = True
                    cache[domain] = io

                # if iqRevise:
                #     ctx = context.copy()
                #     ctx['callby'] = 'RFQ'
                #     io = io.with_context(ctx).action_revised()
                #     cache[domain] = io
                #
                # else:
                vals = self._prepare_IntQuotation(case)
                io = intord_obj.create(vals)
                cache[domain] = io

            IntOrds.append(io.id)
            for ln in io.order_line:
                EnqLnID = ln.enqline_id.id

                # Check: IQ is already been created from this Product.
                if EnqLnID in EnqLnNew.keys():# and not iqRevise:
                    raise Warning(_("Internal Quotation has been created for this Product [%s] \n"
                                    "Please refer the Quotation: %s")%(EnqLnNew[EnqLnID], io.name))

            # if not iqRevise:
            approvedLines = self.env['purchase.order.line'].browse(approvedLines)
            order_line = approvedLines._prepare_RFQlines_IQlines(io)
            io.write({'order_line': order_line})

        if CallBy == 'rfqProd':
            return io.id

        xml_id = 'action_internal_quotations'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('id', 'in', IntOrds))
        result['domain'] = domain
        return result

    @api.multi
    def button_rfq_done(self):
        return self.write({'state':'qtn_received'})


    @api.multi
    def button_mark_Sent(self):
        " Mark as RFQ/PO Mail Sent manually"
        return self.write({'state':'sent'})


    @api.multi
    def button_modify_rfq(self):
        """
        Creates a New RFQ and allows to modify
        """

        case, cr = self, self._cr
        vals = case.copy_data()
        vals = vals and vals[0] or {}

        cr.execute("select count(id) from purchase_order where po_type = 'rfq' and \
                    backorder_id is not null and lead_id = %s and partner_id = %s"%(case.lead_id.id, case.partner_id.id))
        ExistRec = cr.fetchone()
        Cnt = (ExistRec and ExistRec[0] or 0) + 1

        name = str(case.name).split(' - ')
        name = name and name[0] or case.name
        rfqNum = str(name) + " - R" + str(Cnt)
        vals.update({'backorder_id': case.id,
                     'name': rfqNum,
                     'origin': case.origin,
                     })

        newRFQ = self.create(vals)
        self.write({'state': 'rfq_revised'})

        message = _("This RFQ has been revised to: <a href=# data-oe-model=purchase.order data-oe-id=%d>%s</a>") % (newRFQ.id, newRFQ.name)
        self.message_post(body=message)

        message = _("This RFQ has been created from: <a href=# data-oe-model=purchase.order data-oe-id=%d>%s</a>") % (self.id, self.name)
        newRFQ.message_post(body=message)

        xml_id = 'purchase_rfq'
        result = self.env.ref('purchase.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('id', '=', newRFQ.id))
        result['domain'] = domain
        return result



    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new supplier invoice for a purchase order.
        """
        self.ensure_one()
        journal_id = self.env['account.invoice'].default_get(['journal_id'])['journal_id']
        if not journal_id:
            raise UserError(_('Please define an accounting purchase journal for this company.'))

        invoice_vals = {
            # 'name': self.n or '',
            'origin': self.name,
            'type': 'in_invoice',
            'account_id': self.partner_id.property_account_payable_id.id,
            'partner_id': self.partner_id.id,
            'journal_id': journal_id,
            'currency_id': self.currency_id.id,
            # 'comment': self.note,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_id.property_account_position_id.id,
            'company_id': self.company_id.id,
            # 'user_id': self.user_id and self.user_id.id,
            'invoice_line_ids': self.order_line._prepare_invoice_line(),
            'lead_id': self.lead_id.id,
        }
        print ("invoice_vals", invoice_vals['invoice_line_ids'])

        return invoice_vals

    # Inherited
    @api.multi
    def button_done(self):
        res = super(PurchaseOrder, self).button_done()
        print ("--------- button_done ---------")
        print (res)

        Inv_obj = self.env['account.invoice']

        InvVals = self._prepare_invoice()
        Inv_obj.create(InvVals)
        print ("InvVals", InvVals)
        return res



    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            po_type = vals.get('po_type', '')

            if po_type == 'rfq':
                vals['name'] = self.env['ir.sequence'].next_by_code('rfq.order') or '/'
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('purchase.order') or '/'

        r = super(PurchaseOrder, self).create(vals)
        print ("r.po_type :", r.po_type)
        return r
        # return super(PurchaseOrder, self).create(vals)

    @api.multi
    def write(self, vals):
        res = super(PurchaseOrder, self).write(vals)
        context = dict(self._context)

        if vals.get('state', '') == 'sent':

            for case in self:
                StageID = self.env['crm.stage'].get_StageID('rfq_sent')

                ctx = context.copy()
                ctx.update({'sysCall': True})

                if case.po_type == 'rfq' and StageID:
                    case.lead_id.with_context(ctx).write({'stage_id': StageID.id})
        return res



class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Overridden:
    product_id = fields.Many2one('product.product', string='Product', domain=[('purchase_ok', '=', True)]
                                 , change_default=True, required=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
        ('qtn_received', 'Qtn Received')
        ], related='order_id.state', string='Status', readonly=True, index=True, default='draft')


    # New:
    rfq_status = fields.Selection([('approved', 'Approved'),('rejected', 'Rejected')], string="Status")
    enqline_id = fields.Many2one('pq.enquiry.lines', string='Enquiry Lines', ondelete='restrict')
    target_currency_id = fields.Many2one(related='enqline_id.currency_id', relation='res.currency', store=True, string='Target.Price Currency', readonly=True)
    target_price = fields.Float(related='enqline_id.target_price', string='Target Price', store=True, readonly=True, digits=dp.get_precision('Product Price'))
    lead_id = fields.Many2one(related='enqline_id.lead_id', relation='crm.lead', store=True, string='Enquiry')
    po_type = fields.Selection([('rfq', 'RFQ'),('purchase', 'Purchase Order')],
                                    related='order_id.po_type', string='Order Type')
    partner_id = fields.Many2one(related='order_id.partner_id', relation='res.partner', store=True, string='Vendor')
    org_price_unit = fields.Float('Original Unit Price', digits=dp.get_precision('Product Price'), default=0.0, required=True)
    hs_code = fields.Char('HS Code')


    @api.model
    def default_get(self, allfields):
        res = super(PurchaseOrderLine, self).default_get(allfields)
        uom = self.env["product.uom"].search([], limit=1, order='id').id

        res.update({'date_planned': fields.Date.today(),
                    'product_uom': uom})
        return res


    @api.multi
    @api.depends('name', 'order_id')
    def name_get(self):
        result = []
        for case in self:
            RFQ = case.order_id and case.order_id.name or ''
            if RFQ:
                name = RFQ #+ ' [' + case.name  + ']'
            else:
                name = case.name

            result.append((case.id, name))
        return result

    # # Inherited:
    # @api.onchange('product_id')
    # def onchange_product_id(self):
    #     context = dict(self._context)
    #     res = {'value': {}}
    #
    #     if context.get('calledfrm', '') == 'rfq':
    #         if self.product_id and self.product_uom:
    #             if self.product_uom.category_id.id != self.product_id.uom_po_id.category_id.id:
    #                 res['warning'] = {'title': _('Warning'),
    #                                   'message': _('The Product Unit of Measure you chose has a different category than in the product form.')}
    #                 self.product_id = False
    #         return res
    #     return super(PurchaseOrderLine, self).onchange_product_id()


    @api.onchange('org_price_unit')
    def onchange_originalPrice(self):
        context = dict(self._context)
        self.price_unit = self.org_price_unit


    @api.multi
    def button_toggle_approve(self):
        self.ensure_one()

        if not self.product_id:
            raise Warning(_("Please map a Product to proceed !!"))

        elif not self.org_price_unit:
            raise Warning(_("Please enter the Original Unit price to proceed further!!"))

        return self.write({'rfq_status' : 'approved'})

    @api.multi
    def button_toggle_reject(self):
        return self.write({'rfq_status' : 'rejected'})

    @api.multi
    def _prepare_RFQlines_IQlines(self, io):
        lines = []

        for rl in self:
            vals = {}

            EnqQty = rl.enqline_id.product_uom_qty or 1
            RfqQty = rl.product_qty or 1

            if rl.order_id and rl.order_id.partner_id.taxin_cost:
                price = rl.price_total
            else:
                price = rl.price_unit

            price_cost = rl.order_id.currency_id.round((price / RfqQty) * EnqQty)

            for field in ['name', 'product_id', 'product_uom']:
                if rl._fields[field].type == 'many2one':
                    vals[field] = rl[field].id
                else:
                    vals[field] = rl[field] or False

            vals.update({
                'product_uom_qty': EnqQty,
                'rfqline_id' : rl.id,
                'price_unit' : price_cost,
                'price_cost' : price_cost,
                'hs_code' : rl.hs_code,
            })
            lines.append(vals)

        return list(map(lambda x:(0,0,x), lines))

    @api.multi
    def action_create_InternalQtn4lines(self):

        EnqLinesGprd, RfqGrp = {}, {}
        PrevEnquiry = False
        purchase_obj = self.env['purchase.order']

        for idx, case in enumerate(self):
            Enquiry = case.order_id and case.order_id.lead_id or False

            if not Enquiry: continue

            if idx == 0:
                PrevEnquiry = Enquiry.id

            if PrevEnquiry != Enquiry.id:
                raise Warning(_("Please select products belonging to same Enquiry !!"))

            key = (case.enqline_id, Enquiry.id)
            if key not in EnqLinesGprd:
                EnqLinesGprd[key] = {'rfqline': case.id, 'rfq': case.order_id, 'rfqno': case.order_id.name}
            else:
                raise Warning(_("Product '%s' has been selected already, "
                                "from RFQ [%s] !!")%(case.name, EnqLinesGprd.get(key, {}).get('rfqno', '')))


            for k, v in EnqLinesGprd.iteritems():
                key = v.get('rfq', False)
                rfqline = v.get('rfqline', False)

                if not key in RfqGrp:
                    RfqGrp[key] = [rfqline]
                else:
                    RfqGrp[key].append(rfqline)


        IntOrds = []
        for k, v in RfqGrp.iteritems():
            ioID = k.with_context({'selectedRfqLines': v, 'callby': 'rfqProd'}).button_create_InternalQtn()
            IntOrds.append(ioID)

        IntOrds = list(set(IntOrds))

        xml_id = 'action_internal_quotations'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('id', 'in', IntOrds))
        result['domain'] = domain
        return result


    @api.multi
    def _prepare_invoice_line(self):
        """
        Prepare the values to create the new invoice line for a purchase order line.

        """
        res = {}
        lines = []

        for line in self:
            account = line.product_id.property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
            if not account:
                raise UserError(_('Please define expense account for this product: "%s" (id:%d) - or for its category: "%s".') % \
                                (line.product_id.name, line.product_id.id, line.product_id.categ_id.name))

            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.property_account_position_id
            if fpos:
                account = fpos.map_account(account)

            res = {
                'name': line.name,
                'origin': line.order_id.name,
                'account_id': account.id,
                'price_unit': line.price_unit,
                'quantity': line.product_qty,
                'uom_id': line.product_uom.id,
                'product_id': line.product_id.id or False,
                'invoice_line_tax_ids': [(6, 0, line.taxes_id.ids)],
            }
            lines.append(res)

        return list(map(lambda x:(0,0,x), lines))



