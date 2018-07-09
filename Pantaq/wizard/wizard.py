
from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import Warning
import time


class Invite(models.TransientModel):
    _inherit = 'mail.wizard.invite'

    # @api.model
    # def default_get(self, fields):
    #     result = super(Invite, self).default_get(fields)
    #     user_name = self.env.user.name_get()[0][1]
    #     model = result.get('res_model')
    #     res_id = result.get('res_id')
    #
    #     if model == 'crm.lead':
    #         model_name = self.env['ir.model'].search([('model', '=', self.pool[model]._name)]).name_get()[0][1]
    #         document_name = self.env[model].browse(res_id).name_get()[0][1]
    #         message = _('<div><p>Hello,</p><p>%s invited you to follow %s document: %s.</p></div>') % (user_name, 'Enquiry', document_name)
    #         result['message'] = message
    #
    #     return result

    # Overridden:
    @api.multi
    def add_followers(self):
        email_from = self.env['mail.message']._get_default_from()
        for wizard in self:
            Model = self.env[wizard.res_model]
            document = Model.browse(wizard.res_id)

            # filter partner_ids to get the new followers, to avoid sending email to already following partners
            new_partners = wizard.partner_ids - document.message_partner_ids
            new_channels = wizard.channel_ids - document.message_channel_ids
            document.message_subscribe(new_partners.ids, new_channels.ids)

            model_ids = self.env['ir.model'].search([('model', '=', wizard.res_model)])
            model_name = model_ids.name_get()[0][1]

            # send an email if option checked and if a message exists (do not send void emails)
            if wizard.send_mail and wizard.message and not wizard.message == '<br>':  # when deleting the message, cleditor keeps a <br>
                message = self.env['mail.message'].create({
                    'subject': _('Invitation to follow %s: %s') % (model_name, document.name_get()[0][1]),
                    'body': wizard.message,
                    'record_name': document.name_get()[0][1],
                    'email_from': email_from,
                    'reply_to': email_from,
                    'model': wizard.res_model,
                    'res_id': wizard.res_id,
                    'no_auto_thread': True,
                })
                new_partners.with_context(auto_delete=True)._notify(message, force_send=True, user_signature=True)
                message.unlink()
        return {'type': 'ir.actions.act_window_close'}


class wizardRFQ(models.TransientModel):
    _name = "pq.wizard.rfq"
    _description = 'Wizard RFQ'

    lead_id = fields.Many2one('crm.lead', string='Enquiry')
    line_ids = fields.One2many('pq.wizard.rfqlines', 'wiz_id', string='Product Details')
    # linem2m_ids = fields.Many2many('pq.wizard.rfqlines', string='Lines')
    partner_ids = fields.Many2many('res.partner', string='Supplier', domain=[('supplier', '=', True)])

    @api.model
    def default_get(self, fields):
        res = super(wizardRFQ, self).default_get(fields)
        context = dict(self._context or {})
        lead_obj = self.env['crm.lead']

        lead_id = context.get('active_id', False)
        res.update({
            'lead_id': lead_id,
        })
        return res

    @api.multi
    def button_proceed(self):

        # DefSupplierIds = list(map(lambda x: x.id, self.partner_ids))
        supplierIDs = [partner.id for partner in self.partner_ids]

        Lines = self.line_ids
        if not supplierIDs:
            raise Warning(_("Please map atleast one Supplier to create RFQ for the product "))

        partners = self.partner_ids
        vals={}
        for partner in partners:

            vals = {
                'partner_id': partner.id,
                'company_id': self.env.user.company_id.id,
                'lead_id': self.lead_id.id,
                'po_type': 'rfq',
                'currency_id': self.env.user.company_id.currency_id.id
            }

            po = self.env['purchase.order'].create(vals)

            for ln in Lines:
                line_vals = {
                    'name': ln.name,
                    'product_qty': ln.product_uom_qty,
                    'product_id': ln.product_id.id,
                    'product_uom': ln.product_uom.id,
                    'price_unit': ln.product_id.lst_price,
                    # 'date_planned': date_planned,
                    # 'taxes_id': [(6, 0, taxes_id.ids)],
                    # 'procurement_ids': [(4, self.id)],
                    'order_id': po.id,
                }
                po_lines = self.env['purchase.order.line'].create(line_vals)





        # commented because no procurement oreder present in odoo 11.

        # if not Lines:
        #     raise Warning(_("Please add Product Details to proceed further!!"))
        #
        # for ln in Lines:
        #
        #     if not ln.partner_ids and not DefSupplierIds:
        #         raise Warning(_("Please map atleast one Supplier to create RFQ for the product [%s]")%(ln.product_id.name))
        #
        #
        #     supplierIDs = list(map(lambda x: x.id, ln.partner_ids))
        #     supplierIDs += DefSupplierIds
        #     supplierIDs = list(set(supplierIDs))
        #
        #     ln._PQ_action_procurement_create(supplierIDs=supplierIDs)



        xml_id = 'purchase_rfq'
        result = self.env.ref('purchase.%s' % (xml_id)).read()[0]
        domain = eval(result['domain'])
        domain.append(('lead_id', '=', self.lead_id.id))
        domain.append(('state','=', 'draft'))
        domain.append(('partner_id', 'in', supplierIDs))
        result['domain'] = domain
        return result


class wizardRFQLines(models.TransientModel):
    _name = "pq.wizard.rfqlines"
    _description = 'Wizard RFQ Lines'

    wiz_id = fields.Many2one('pq.wizard.rfq', string='Wiz RFQ', ondelete='cascade')
    name = fields.Text(string='Description', required=True)

    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)])
    product_uom_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True, default=1.0)
    product_uom = fields.Many2one('product.uom', string='Unit of Measure', required=True)
    partner_ids = fields.Many2many('res.partner', string='Supplier', domain=[('supplier', '=', True)])
    enqln_id = fields.Many2one('pq.enquiry.lines', string='EnquiryLine ID')
    lead_id = fields.Many2one('crm.lead', string='Enquiry')

    has_targetprice = fields.Boolean('I have Target Price')
    target_price = fields.Float('Targeted Price / Unit', help="Enter Target Price for a unit.")
    currency_id = fields.Many2one('res.currency', 'Currency',
                    default=lambda self: self.env.user.company_id.currency_id)


    @api.multi
    def _prepare_enquiryline_procurement(self, group_id=False):
        self.ensure_one()

        targetPrice = self.currency_id.compute(self.target_price, self.env.user.company_id.currency_id)

        return {
            'name' : self.name,
            'origin' : self.lead_id.enq_number,
            'product_id' : self.product_id.id,
            'product_qty' : self.product_uom_qty,
            'product_uom' : self.product_uom.id,
            'company_id' : self.env.user.company_id.id,
            'target_price': targetPrice,
            'enqline_id' : self.enqln_id.id,
            'lead_id' : self.lead_id.id,
        }


    @api.multi
    def _PQ_action_procurement_create(self, supplierIDs=[]):
        # Replicated from Sale

        # """
        # Create procurements based on quantity ordered. If the quantity is increased, new
        # procurements are created. If the quantity is decreased, no automated action is taken.
        # """

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        new_procs = self.env['procurement.order'] #Empty recordset

        for line in self:
            vals = line._prepare_enquiryline_procurement()

            vals['product_qty'] = line.product_uom_qty
            vals['partner_ids'] = [(6, 0, supplierIDs)]
            new_proc = self.env["procurement.order"].create(vals)
            new_procs += new_proc
        new_procs.run()
        return new_procs

    @api.multi
    def button_edit(self):
        'button edit'



class ProductCompare(models.TransientModel):
    _name = "pq.wiz.rfq.productcompare"
    _description = 'Wizard RFQ products compare'

    lead_id = fields.Many2one('crm.lead', string='Enquiry', domain="[('state', '=', 'done')]", required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id)
    line_ids = fields.One2many('pq.wiz.rfq.productcompare.lines', 'wiz_id', string='Lines')


    @api.multi
    def button_proceed(self):

        self.ensure_one()
        cr = self._cr

        cr.execute("delete from pq_wiz_rfq_productcompare_lines where create_uid = %s"%(self._uid))

        poln_obj = self.env['purchase.order.line']
        wizln_obj = self.env['pq.wiz.rfq.productcompare.lines']

        cr.execute("""
                    select l.id
                    from purchase_order po
                    inner join purchase_order_line l on po.id = l.order_id
                    where po.lead_id = %s
                  """%(self.lead_id.id))

        lnids = list(map(lambda x: x[0], cr.fetchall()))
        polnIDs = poln_obj.browse(lnids)

        for ln in polnIDs:
            vals = ln.copy_data()
            vals = vals and vals[0] or {}
            vals.update({
                'wiz_id' : self.id,
                'rfqline_id' : ln.id,
                'currency_id': self.currency_id.id,

                'price_subtotal': ln.price_subtotal,
                'price_total' : ln.price_total,
                         })

            wizln_obj.create(vals)

        xml_id = 'action_rfqcomparelines_form'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        result['domain'] = [('wiz_id', '=', self.id)]
        result['name'] = 'NAME ***'
        return result




class ProductCompareLines(models.TransientModel):
    _name = "pq.wiz.rfq.productcompare.lines"
    _description = 'Wizard RFQ products compare'


    @api.depends('product_qty', 'price_unit', 'currency_id')
    def _compute_amount(self):
        for line in self:
            ToCurrency = line.currency_id
            now = time.strftime('%Y-%m-%d')
            ctx = {'date' : now}

            line.update({
                # 'org_price_unit1': 55,
                'price_unit1' : line.rfq_currency_id.with_context(ctx).compute(line.price_unit, ToCurrency),
                'price_total1' : line.rfq_currency_id.with_context(ctx).compute(line.price_total, ToCurrency),
                'price_subtotal1': line.rfq_currency_id.with_context(ctx).compute(line.price_subtotal, ToCurrency),

            })


    wiz_id = fields.Many2one('pq.wiz.rfq.productcompare', string='Wiz', ondelete='cascade')
    name = fields.Text(string='Product Description', readonly=True)
    product_qty = fields.Float(string='RFQ Qty', digits=dp.get_precision('Product Unit of Measure'), readonly=True)
    partner_id = fields.Many2one(relation='res.partner', related='order_id.partner_id', string='Vendor', store=True, readonly=True)

    order_id = fields.Many2one('purchase.order', string='RFQ Reference', readonly=True)
    rfqline_id = fields.Many2one('purchase.order.line', string='RFQ Line Reference', readonly=True)
    enqline_id = fields.Many2one('pq.enquiry.lines', string='Enquiry Lines', readonly=True)
    lead_id = fields.Many2one(related='enqline_id.lead_id', relation='crm.lead', string='Enquiry', readonly=True)
    enqln_qty = fields.Float(related='enqline_id.product_uom_qty', digits=dp.get_precision('Product Unit of Measure'), string='Requested Qty', readonly=True)

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', readonly=True)

    rfq_status = fields.Selection([('approved', 'Approved'),('rejected', 'Rejected')], string="Status", readonly=True)
    company_id = fields.Many2one(relation='res.company', related='order_id.company_id', string='Company', readonly=True)

    # org_price_unit = fields.Float('Original Unit Price', readonly=True)

    price_unit = fields.Float(string='Final Unit Price', readonly=True)
    price_subtotal = fields.Float(string='Subtotal', readonly=True)
    price_total = fields.Float(string='Total', readonly=True)
    rfq_currency_id = fields.Many2one(relation='res.currency', related='order_id.currency_id', string='Currency', readonly=True)

    # org_price_unit1 = fields.Float(compute='_compute_amount', string='Original Unit Price', readonly=True)
    price_unit1 = fields.Float(compute='_compute_amount', string='Final Unit Price', readonly=True, store=True)
    price_subtotal1 = fields.Monetary(compute='_compute_amount', string='Subtotal', readonly=True, store=True,
                                      help="Subtotal (without Tax)")
    price_total1 = fields.Monetary(compute='_compute_amount', string='Total', readonly=True, store=True,
                                   help="Total (with Tax)")
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)


    @api.multi
    def button_toggle_approve(self):
        self.write({'rfq_status' : 'approved'})
        return self.rfqline_id.write({'rfq_status' : 'approved'})

    @api.multi
    def button_toggle_reject(self):
        self.write({'rfq_status' : 'rejected'})
        return self.rfqline_id.write({'rfq_status' : 'rejected'})

    @api.multi
    def action_process_RFQLines(self):

        context = self._context
        rfq_obj = self.env['purchase.order.line']

        active_id = context.get('active_id', False)
        actrec = self.browse(active_id)

        if not actrec.wiz_id: return True

        apprLn = []

        for ln in actrec.wiz_id.line_ids:
            if ln.rfq_status == 'approved':
                apprLn.append(ln.rfqline_id.id)

        rfqLns = rfq_obj.browse(apprLn)
        return rfqLns.action_create_InternalQtn4lines()




class AskRevision(models.TransientModel):
    _name = "pq.wiz.ask.revision"
    _description = 'Ask for revision'

    note = fields.Html('Note')


    @api.multi
    def button_proceed(self):
        context = dict(self._context)

        res_model = context.get('active_model', '')
        res_id = context.get('active_id', False)

        if not res_model or not res_id:
            return False

        res_pool = self.env[res_model].browse(res_id)

        Partners = list(map(lambda x: x.id, res_pool.lead_id.team_proc_id.member_ids))

        for case in self:
            body_html = "<div><b>%(title)s</b></div>%(note)s" % {
                'title': _('Asked for Revision'),
                'note': case.note or '',
            }
            res_pool.message_post(body_html,
                                  partner_ids= [(4, pid) for pid in Partners])
        return True



class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"


    # Overriden:
    @api.multi
    def create_invoices(self):
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))

        if self.advance_payment_method == 'delivered':
            sale_orders.action_invoice_create()
        elif self.advance_payment_method == 'all':
            sale_orders.action_invoice_create(final=True)
        else:
            # Create deposit product if necessary
            if not self.product_id:
                vals = self._prepare_deposit_product()
                self.product_id = self.env['product.product'].create(vals)
                self.env['ir.values'].sudo().set_default('sale.config.settings', 'deposit_product_id_setting', self.product_id.id)

            sale_line_obj = self.env['sale.order.line']
            for order in sale_orders:
                if self.advance_payment_method == 'percentage':
                    amount = order.amount_untaxed * self.amount / 100
                else:
                    amount = self.amount
                if self.product_id.invoice_policy != 'order':
                    raise UserError(_('The product used to invoice a down payment should have an invoice policy set to "Ordered quantities". Please update your deposit product to be able to create a deposit invoice.'))
                if self.product_id.type != 'service':
                    raise UserError(_("The product used to invoice a down payment should be of type 'Service'. Please use another product or update this product."))
                if order.fiscal_position_id and self.product_id.taxes_id:
                    tax_ids = order.fiscal_position_id.map_tax(self.product_id.taxes_id).ids
                else:
                    tax_ids = self.product_id.taxes_id.ids
                so_line = sale_line_obj.create({
                    'name': _('Advance: %s') % (time.strftime('%m %Y'),),
                    'price_unit': amount,
                    'product_uom_qty': 0.0,
                    'order_id': order.id,
                    'discount': 0.0,
                    'product_uom': self.product_id.uom_id.id,
                    'product_id': self.product_id.id,
                    'tax_id': [(6, 0, tax_ids)],
                })
                self._create_invoice(order, so_line, amount)

        print ("came !!!!!!!!!!!!!!!!!")
        #self.send_invoices_xero()

        if self._context.get('open_invoices', False):
            return sale_orders.action_view_invoice()
        return {'type': 'ir.actions.act_window_close'}

    @api.multi
    def send_invoices_xero(self):
        wizConnect = self.env["wiz.connect.xero"]

        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        invoice_ids = sale_orders.mapped('invoice_ids').ids

        ctx = dict(self._context)
        ctx.update({'invoiceIds': invoice_ids })
        wizConnect.with_context(ctx).action_export_invoices()

        return True