
from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from lxml import etree
from odoo.osv.orm import setup_modifiers
from odoo.exceptions import Warning

class InternalOrder(models.Model):
    _name = "internal.order"
    _inherit = ['mail.thread']
    _description = "Internal Quotation"
    _order = 'date_order desc, id desc'



    @api.model
    def fields_view_get(self, view_id=None, view_type=False, toolbar=False, submenu=False):
        PurchaseGrp = self.user_has_groups('purchase.group_purchase_user')

        res = super(InternalOrder, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        doc = etree.XML(res['arch'])

        # print ("res['fields']")
        # for r in res['fields'].keys():
        #
        #     if r == 'order_line':
        #         print ("......", r)
        #         print (res['fields'][r].keys())

        if PurchaseGrp and view_type == 'form':
            print ("... inside ...")
            for node in doc.xpath("//field[@name='target_price']"):
                print ("... found the node ...")
                # node = doc.xpath("//field[@name='method_end']")[0]
                # node.set('invisible', '1')
                # setup_modifiers(node, result['fields']['method_end'])

                node.set('string', 'Target Price Proc')
                setup_modifiers(node, res['fields']['currency_id'])


        res['arch'] = etree.tostring(doc)
        return res



    @api.depends('currency_id','order_line.price_total')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """
        print ("---------------------- IQ <called>----------------------")
        for order in self:

            order_currency = order.currency_id
            ctx = {'date' : order.date_order}

            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:

                # amount_untaxed += line.rfq_currency_id.with_context(ctx).compute(line.price_subtotal, order_currency)
                # amount_tax += line.rfq_currency_id.with_context(ctx).compute(line.price_tax, order_currency)

                amount_untaxed += line.currency_id.with_context(ctx).compute(line.price_subtotal, order_currency)
                amount_tax += line.currency_id.with_context(ctx).compute(line.price_tax, order_currency)

                print ("IQ_currency", line.currency_id.name, order_currency.id, order_currency.name, ctx)
                print ("untax == ", line.price_subtotal, amount_untaxed)

            print ("-------------------------------------------------------")
            order.update({
                'amount_untaxed': order.currency_id.round(amount_untaxed),
                'amount_tax': order.currency_id.round(amount_tax),
                'amount_total': amount_untaxed + amount_tax,
            })

    @api.model
    def _get_default_team(self):
        default_team_id = self.env['crm.team']._get_default_team_id()
        print ("default_team_id", default_team_id)
        return default_team_id
        # return self.env['crm.team'].browse(default_team_id)



    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    origin = fields.Char(string='Source Document', help="Reference of the document that generated this sales order request.")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('quoted', 'Quoted'),
        ('done', 'Accepted'),
        ('rejected', 'Rejected'),
        ('revised', 'IQ Revised'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')
    date_order = fields.Datetime(string='Quote Date', required=True, readonly=True, index=True, states={'draft': [('readonly', False)]}, copy=False, default=fields.Datetime.now)
    validity_date = fields.Date(string='Due Date', readonly=True, states={'draft': [('readonly', False)]})
    create_date = fields.Datetime(string='Creation Date', readonly=True, index=True, help="Date on which sales order is created.")

    user_id = fields.Many2one('res.users', string='Owner', index=True, track_visibility='onchange', default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True, states={'draft': [('readonly', False)], 'submit': [('readonly', False)]}, required=True,
			change_default=True, index=True)

    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True, required=True, states={'draft': [('readonly', False)]},
                                  default=lambda self: self.env.user.company_id.currency_id, track_visibility='onchange')

    order_line = fields.One2many('internal.order.line', 'order_id', string='Order Lines', readonly=True, states={'draft': [('readonly', False)]}, copy=True)

    note = fields.Text('Terms and conditions', default=lambda self: self.env.user.company_id.sale_note)
    remarks = fields.Text('Remarks')

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', track_visibility='always')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all', track_visibility='always')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', track_visibility='always')

    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.user.company_id)
    team_id = fields.Many2one('crm.team', 'Sales Team', change_default=True, default=_get_default_team, oldname='section_id')

    product_id = fields.Many2one('product.product', related='order_line.product_id', string='Product')
    lead_id = fields.Many2one('crm.lead', string='Enquiry', ondelete='restrict')
    salesman_id = fields.Many2one(related='lead_id.user_id', relation='res.users', store=True, string='Sales Person', readonly=True)
    backorder_id = fields.Many2one('internal.order', string='BackOrder', index=True, help="Original IQ mapped against each revised IQs")
    is_rejected = fields.Boolean('Is Rejected by Customer?', copy=False)


    @api.multi
    def _add_followers_notify(self):
        """
            Add Members of the Team as followers and notify the same
            by sending invitation mail
        """
        self.ensure_one()
        WizInvite_obj = self.env['mail.wizard.invite']

        mappedPartner = map(lambda x: x.partner_id.id, self.message_follower_ids)

        InvPartnerIDs = []
        for tu in self.lead_id.team_id.member_ids:
            if tu.partner_id.id in mappedPartner: continue
            InvPartnerIDs.append(tu.partner_id.id)

        InvPartnerIDs.append(self.lead_id.user_id.partner_id.id)
        InvPartnerIDs = list(set(InvPartnerIDs))

        user_name = self.env.user.name_get()[0][1]
        wizvals = {}
        message = _('<div><p>Hello,</p><p>%s has submitted the Internal Quotation %s, for the Enquiry %s .</p></div>') % (user_name, self.name, self.lead_id.enq_number)
        wizvals.update({'res_model': self._name,
                        'res_id'   : self.id,
                        'partner_ids': [(6,0,InvPartnerIDs)],
                        'send_mail' : True,
                        'message' : message,
                        })
        wizRec = WizInvite_obj.create(wizvals)

        return wizRec.add_followers()

    @api.multi
    def _get_reporting_manger(self):
        self.ensure_one()
        cr = self._cr
        emp_obj = self.env['hr.employee']

        manager = False
        parentUIDs = []

        for emp in emp_obj.search([('user_id', '=', self.user_id.id)], limit=1):
            manager = emp.parent_id

            cr.execute("""

                    select user_id
                    from hr_employee e
                    inner join resource_resource r on r.id = e.resource_id
                    where e.id in
                        (
                            SELECT id FROM connectby('hr_employee', 'parent_id', 'id', 'id', %s::text, 0)
                            AS t(id int, parent_id int, level int, name int)
                            WHERE parent_id is not null
                        )
                    """%(emp.id))
            mgrUIDs = map(lambda x: x[0], cr.fetchall())

        return manager, parentUIDs


    @api.multi
    def action_submit(self):
        self.ensure_one()
        cr = self._cr

        Config = self.env["ir.config_parameter"]
        thresholdMU = float(Config.sudo().get_param('purchase_markup', default='0'))
        manager, parentUIDs = self._get_reporting_manger()

        user = self.env['res.users'].browse(self._uid)

        approveFlag = waitFlag = RejFlag = False
        for case in self:
            for line in case.order_line:
                ProdName = line.product_id.name_get()[0][1]

                if not line.margin_perc:
                    raise Warning(_("Please enter margin for the product [%s]!!"%(ProdName)))

                elif (line.margin_perc < thresholdMU) and line.approval_state not in ('approved', 'awaiting', 'rejected'):
                    approveFlag = True
                    line.write({'approval_state':'awaiting'})

                elif (line.approval_state == 'awaiting'):
                    waitFlag = True

                elif (line.approval_state == 'rejected'):
                    RejFlag = True
            if approveFlag:
                if not manager:
                    raise Warning(_("Please map a Manager under Employee for approval process to proceed further!!"))

                print ("....manager", manager)
                subject = 'Need Approval for IQ: %s'%(case.name)
                body = 'Margin set by %s in the Internal Quotation %s needs your approval.'%(user.name, case.name)

                # Notify via Mail:
                case.message_post(body=body, subject=subject, message_type='comment',
                            subtype='mail.mt_comment', attachments=[],
                            partner_ids=[manager.user_id.partner_id.id],
                            content_subtype='html')

                return True

            elif waitFlag and user.id not in parentUIDs:
                raise Warning(_("You cannot submit this Qtn, Waiting for Approval from your Manager, %s !!"%manager.name))

            elif RejFlag:
                raise Warning(_("Margin set for below the product(s) are Rejected by your Manager, Please create a Revised Qtn"))

            case.write({'state': 'submit'})
            case._send_mail_notify(action='submit')

        return True


    @api.multi
    def _send_mail_notify(self, action='submit'):
        self.ensure_one()

        SalesPartners = list(map(lambda x: x.partner_id.id, self.lead_id.team_id.member_ids))
        ProcPartners = list(map(lambda x: x.partner_id.id, self.lead_id.team_proc_id.member_ids))
        NotifyPartners = []

        MsgBody = ''
        # force_send = True

        print ("_send_mail_notify", action)

        if action == 'submit':
            # template = self.env.ref('Pantaq.email_intqtn_submit')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners]}
            # template.send_mail(self.id, force_send=force_send, email_values=email_values)

            MsgBody = 'Internal Quotation has been Submitted.'
            NotifyPartners = list(ProcPartners)

        elif action == 'revise':
            # template = self.env.ref('Pantaq.email_intqtn_revised')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners + SalesPartners]}
            # template.send_mail(self.id, force_send=False, email_values=email_values)

            MsgBody = 'Internal Quotation has been Revised.'
            NotifyPartners = list(ProcPartners + SalesPartners)

        elif action == 'reject':
            # template = self.env.ref('Pantaq.email_intqtn_rejected')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners + SalesPartners]}
            # template.send_mail(self.id, force_send=False, email_values=email_values)

            MsgBody = 'Internal Quotation has been Rejected.'
            NotifyPartners = list(ProcPartners + SalesPartners)

        elif action == 'cancel':
            # template = self.env.ref('Pantaq.email_intqtn_cancelled')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners + SalesPartners]}
            # template.send_mail(self.id, force_send=False, email_values=email_values)

            MsgBody = 'Internal Quotation has been Cancelled.'
            NotifyPartners = list(ProcPartners + SalesPartners)

        return self._notify_by_chat(MsgBody, NotifyPartners)


    @api.multi
    def _notify_by_chat(self, message='', Partners=[]):
        return self.env['mail.message'].create({
            'model': self._name,
            'res_id': self.id or False,
            'body': message,
            'partner_ids': [(4, pid) for pid in Partners],
            'needaction_partner_ids': [(4, pid) for pid in Partners],
            'force_display': True,
        })

    @api.multi
    def action_draft(self):
        self.write({'state': 'draft'})

    @api.multi
    def action_done(self):
        self.write({'state': 'done'})

    @api.multi
    def action_cancel(self):
        self.write({'state': 'cancel'})
        return self._send_mail_notify(action='cancel')

    @api.multi
    def action_rejected(self):
        self.write({'state': 'rejected'})
        websiteCall = self._context.get('websiteCall', False)
        if websiteCall:
            return True

        return self._send_mail_notify(action='reject')


    @api.multi
    def action_revised(self):
        self.ensure_one()
        cr, context = self._cr, dict(self._context)

        CallBy = context.get('callby', '')

        vals = self.copy_data()
        vals = vals and vals[0] or {}

        self.write({'state': 'revised', 'is_rejected':False})

        cr.execute("select count(id) from internal_order where \
                    backorder_id is not null and lead_id = %s"%(self.lead_id.id))
        ExistRec = cr.fetchone()
        Cnt = (ExistRec and ExistRec[0] or 0) + 1

        name = str(self.name).split(' - ')
        name = name and name[0] or self.name
        RefNum = str(name) + " - R" + str(Cnt)
        vals.update({'backorder_id': self.id,
                     'name' : RefNum,
                     'origin': self.origin,
                     })

        newID = self.create(vals)
        self._send_mail_notify(action='revise')

        template = self.env.ref('Pantaq.email_intqtn_revised').id
        self.message_post_with_template(template, composition_mode='comment')

        self.message_post(body=_("Internal Quotation has been Revised"))
        newID.message_post_with_view('mail.message_origin_link',
            values={'self': newID, 'origin': self},
            subtype_id=self.env['ir.model.data'].xmlid_to_res_id('mail.mt_note'))

        if CallBy == 'RFQ':
            return newID

        xml_id = 'action_internal_quotations'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('id', '=', newID.id))
        result['domain'] = domain
        return result


    @api.multi
    def button_dummy(self):
        return True

    @api.one
    def _get_pricelist(self, Currency, Company):
        self.ensure_one()
        cr = self._cr

        priceID = DefPriceID = False

        cr.execute("select id, company_id from product_pricelist where currency_id = %s "
                   "and active is true order by company_id "%(Currency.id))

        for pp in cr.dictfetchall():

            if pp['company_id'] == Company.id:
                priceID = pp['id']
                break

            elif not pp['company_id']:
                DefPriceID = pp['id']

        priceID = priceID if priceID else DefPriceID

        # Create Pricelist when not found for that currency
        if not priceID:
            priceID = self.env['product.pricelist'].create({'name': 'Pricelist ' + str(Currency.name),
                                                           'currency_id': Currency.id
                                                          })
            priceID = priceID.id

        return priceID



    @api.model
    def _prepare_CustQuote(self):
        """ Prepare the dict of values to create the new Sales Order from the RFQ.
        """
        self.ensure_one()
        case = self
        vals = {}

        for field in ['date_order', 'partner_id', 'note', 'company_id', 'lead_id', 'currency_id']:
            if case._fields[field].type == 'many2one':
                vals[field] = case[field].id
            else:
                vals[field] = case[field] or False

        priceID = case._get_pricelist(case.currency_id, case.company_id)
        priceID = priceID[0]

        vals.update({'origin'     : case.lead_id.enq_number,
                     'sale_type'  : 'quote',
                     'order_line' : case.order_line._prepare_IQLines_CQLines(),
                     'pricelist_id' : priceID,
                     'intorder_id'  : case.id,
                     })
        return vals


    @api.multi
    def action_create_CustQuote(self):
        """
            Creates Customer Quote
        """
        sale_obj = self.env['sale.order']

        CQids = []
        cache = {}

        for case in self:
            EnquiryRec = case.lead_id
            vals = self._prepare_CustQuote()

            domain = (
                    ('state', 'in', ('sale', 'done')),
                    ('lead_id', '=', EnquiryRec.id),
                    ('sale_type', '=', 'internal'),
                    )
            cq = sale_obj.search([dom for dom in domain], order='id desc', limit=1)

            # Check: Revision
            if cq:
                cq = cq[0]
                ctx = context.copy()
                ctx['callby'] = 'auto'
                cq = cq.with_context(ctx).action_revised()
                CQids.append(cq.id)
            else:
                newRec = sale_obj.create(vals)
                CQids.append(newRec.id)

        self.write({'state': 'quoted'})

        xml_id = 'action_cust_quote'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('id', 'in', CQids))
        result['domain'] = domain
        return result


    @api.model
    def create(self, vals):
        context = dict(self._context)
        type = context.get('type', '')

        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('internal.sale.order') or 'New'

        if vals.get('lead_id', False):
            StageID = self.env['crm.stage'].get_StageID('io_created')

            ctx = context.copy()
            ctx.update({'sysCall': True})

            if StageID:
                self.env['crm.lead'].browse(vals['lead_id']).with_context(ctx).write({'stage_id': StageID.id})

        return super(InternalOrder, self).create(vals)


class InternalOrderLine(models.Model):
    _name = 'internal.order.line'
    _description = 'Internal Quotation Line'

    @api.depends('product_uom_qty', 'discount_perc', 'discount', 'price_unit', 'tax_id', 'margin', 'margin_perc')
    def _compute_amount(self):
        """
        Compute the amounts of the Internal Qtn line.
        """
        for line in self:
            line.onchange_onAmount()
            # order = line.order_id
            # price = line.price_cost
            #
            # margin   = line.margin
            # discount = line.discount
            #
            # # if line.margin_perc:
            # #     margin = order.currency_id.round(price * ((line.margin_perc or 0.0) / 100.0))
            # #     line.update({'margin':margin})
            #
            # price += margin
            #
            # # print "line.price_unit", line.price_unit, price
            # # if price != line.price_unit:
            # #     print "s", price
            # #     line.update({'price_unit':price})
            #
            # # if line.discount_perc:
            # #     discount = order.currency_id.round(price * ((line.discount_perc or 0.0) / 100.0))
            # #     line.update({'discount':discount})
            #
            # price -= discount
            #
            # taxes = line.tax_id.compute_all(price, order.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_id)
            # line.update({
            #     'price_tax': taxes['total_included'] - taxes['total_excluded'],
            #     'price_total': taxes['total_included'],
            #     'price_subtotal': taxes['total_excluded'],
            # })



    @api.depends('approval_state')
    def _visible_approval(self):
        """
        Compute the flag, to enable approval/rejection button on the form for Manager
        """
        Aflag = Rflag = False

        emp_obj = self.env['hr.employee']
        for case in self:
            cr = case._cr
            empID = emp_obj.search([('user_id', '=', case.user_id.id)], limit=1)

            mgrUIDs = []
            if empID:
                cr.execute("""

                        select user_id
                        from hr_employee e
                        inner join resource_resource r on r.id = e.resource_id
                        where e.id in
                            (
                                SELECT id FROM connectby('hr_employee', 'parent_id', 'id', 'id', %s::text, 0)
                                AS t(id int, parent_id int, level int, name int)
                                WHERE parent_id is not null
                            )
                        """%(empID.id))
                mgrUIDs = list(map(lambda x: x[0], cr.fetchall()))

            if case.approval_state in ('awaiting', 'rejected') and case._uid in mgrUIDs:
                Aflag = True

            if case.approval_state in ('awaiting', 'approved') and case._uid in mgrUIDs:
                Rflag = True

            case.show_approval = Aflag
            case.show_reject = Rflag


    order_id = fields.Many2one('internal.order', string='Order Reference', required=True, ondelete='cascade', index=True, copy=False)
    name = fields.Text(string='Description', required=True)

    price_unit = fields.Float('Unit Price', required=True, digits=dp.get_precision('Product Price'), default=0.0)
    price_cost = fields.Float('Cost', readonly=True, required=True, digits=dp.get_precision('Product Price'), default=0.0)

    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', readonly=True, store=True)
    price_tax  = fields.Monetary(compute='_compute_amount', string='Taxes', readonly=True, store=True)
    price_total = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True)

    sales_price_cost = fields.Monetary(compute='_compute_amount', string='Cost for SalesTeam', readonly=True, store=True)

    tax_id = fields.Many2many('account.tax', string='Taxes')

    discount_perc = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'), default=0.0)
    discount = fields.Float(string='Discount', digits=dp.get_precision('Discount'), default=0.0)
    margin_perc = fields.Float(string='Margin (%)', digits=dp.get_precision('Discount'), default=0.0)
    margin = fields.Float(string='Margin', digits=dp.get_precision('Discount'), default=0.0)

    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], change_default=True, ondelete='restrict', required=True)
    product_uom_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True, default=1.0)
    product_uom = fields.Many2one('product.uom', string='Unit of Measure', required=True)

    user_id = fields.Many2one(related='order_id.user_id', relation='res.users', store=True, string='Owner', readonly=True)
    salesman_id = fields.Many2one(related='order_id.salesman_id', relation='res.users', store=True, string='Sales Person', readonly=True)
    # currency_id = fields.Many2one(related='order_id.currency_id', store=True, string='Currency', readonly=True)
    company_id = fields.Many2one(related='order_id.company_id', relation='res.company', string='Company', store=True, readonly=True)
    rfqline_id = fields.Many2one('purchase.order.line', string='RFQ Product Reference', readonly=True)
    # rfq_currency_id = fields.Many2one(related='rfqline_id.currency_id', store=True, string='RFQ Currency', readonly=True)
    currency_id = fields.Many2one(related='rfqline_id.currency_id', relation='res.currency', store=True, string='Currency', readonly=True, help='Currency is quoted w.r.t RFQ')
    enqline_id = fields.Many2one(related='rfqline_id.enqline_id', relation='pq.enquire.lines', store=True, string='Enquiry Product')
    supplier_id = fields.Many2one(related='rfqline_id.partner_id', relation='res.partner', store=True, string='Vendor', readonly=True)
    vendor_type = fields.Selection([('manufacturer', 'Manufacturer'), ('reseller', 'Reseller')], string="Vendor Type"
                                                    , related='supplier_id.vendor_type', default='reseller', readonly=True)
    hs_code = fields.Char(string='HS Code')

    target_currency_id = fields.Many2one(related='enqline_id.currency_id', relation='res.currency', store=True, string='Target Price Currency', readonly=True)
    target_price = fields.Float(related='enqline_id.target_price', string='Target Cost', store=True, readonly=True, digits=dp.get_precision('Product Price'))

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], related='order_id.state', string='Order Status', readonly=True, copy=False, store=True, default='draft')

    approval_state = fields.Selection([
                ('awaiting', 'Awaiting'),
                ('approved', 'Approved'),
                ('rejected', 'Rejected'),], string='Approval Status', readonly=True, copy=False, default='awaiting')
    show_approval = fields.Boolean('Show Approve Button', compute='_visible_approval', readonly=False)
    show_reject = fields.Boolean('Show Reject Button', compute='_visible_approval', readonly=False)

    @api.multi
    @api.onchange('product_id')
    def onchange_product(self):
        if not self.product_id:
            return {'domain': {'product_uom': []}}

        vals = {}
        domain = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
        if not self.product_uom or (self.product_id.uom_id.category_id.id != self.product_uom.category_id.id):
            vals['product_uom'] = self.product_id.uom_id

        product = self.product_id

        name = product.name_get()[0][1]
        if product.description_sale:
            name += '\n' + product.description_sale
        vals['name'] = name

        self.update(vals)
        return {'domain': domain}


    @api.multi
    @api.onchange('product_uom_qty', 'discount_perc', 'discount', 'price_unit', 'tax_id', 'margin', 'margin_perc')
    def onchange_onAmount(self):
        vals = {}
        order = self.order_id
        price = self.price_cost

        margin = self.margin
        discount = self.discount

        if self.margin_perc:
            margin = order.currency_id.round(price * ((self.margin_perc or 0.0) / 100.0))
            vals.update({'margin':margin})

        price += margin

        if price != self.price_unit:
            vals.update({'price_unit':price})

        if self.discount_perc:
            discount = order.currency_id.round(price * ((self.discount_perc or 0.0) / 100.0))
            vals.update({'discount':discount})

        price -= discount

        taxes = self.tax_id.compute_all(price, order.currency_id, self.product_uom_qty, product=self.product_id, partner=self.order_id.partner_id)
        vals.update({
            'price_tax': taxes['total_included'] - taxes['total_excluded'],
            'price_total': taxes['total_included'],
            'price_subtotal': taxes['total_excluded'],
            'sales_price_cost': order.currency_id.round(taxes['total_excluded'] / self.product_uom_qty),
        })
        self.update(vals)
        return {}

    @api.multi
    def _prepare_IQLines_CQLines(self):
        res = []

        for case in self:
            vals = {}
            includeTax = case.company_id.include_tax_iq

            order_currency = case.order_id.currency_id
            ctx = {'date' : case.order_id.date_order}

            for field in ['name', 'product_id', 'product_uom_qty', 'product_uom', 'enqline_id']:
                if case._fields[field].type == 'many2one':
                    vals[field] = case[field].id
                else:
                    vals[field] = case[field] or False

            if includeTax:
                price = case.price_total
            else:
                price = case.price_subtotal

            # price = case.rfq_currency_id.with_context(ctx).compute(price, order_currency)
            price = case.currency_id.with_context(ctx).compute(price, order_currency)

            price_cost = case.currency_id.round(price / case.product_uom_qty)
            vals.update({'price_cost': price_cost,
                         'price_unit': price_cost,
                         'currency_id': order_currency.id
                         })

            res.append(vals)
        return list(map(lambda x:(0,0,x), res))


    @api.multi
    def button_toggle_approve(self):
        self.ensure_one()
        msg = "Margin of %s %% for the product [%s] has been Approved."%(self.margin, self.product_id.name)
        self.order_id.message_post(body = msg)
        return self.write({'approval_state' : 'approved'})

    @api.multi
    def button_toggle_reject(self):
        self.ensure_one()
        msg = "Margin of %s %% for the product [%s] has been Rejected."%(self.margin, self.product_id.name)
        self.order_id.message_post(body = msg)
        return self.write({'approval_state' : 'rejected'})

