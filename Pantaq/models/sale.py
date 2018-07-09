
from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp


class SaleOrder(models.Model):
    _inherit = ['sale.order']

    @api.model
    def fields_view_get(self, view_id=None, view_type=False, toolbar=False, submenu=False):

        def get_view_id(name):
            view = self.env['ir.ui.view'].search([('name', '=', name)], limit=1)
            if not view:
                return False
            return view.id

        context = dict(self._context)
        sale_type = context.get('sale_type', 'order')

        if view_type == 'form' and sale_type == 'quote':
            view_id = get_view_id('pq_view_cust_quote_form')
        else:
            view_id = get_view_id('view_order_form')

        return super(SaleOrder, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
    #
    # # Overridden:
    # @api.depends('currency_id')
    # def _amount_all(self):
    #     """
    #     Compute the total amounts of the SO.
    #     """
    #
    #     print (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>.. _amount_all (overridden) **")
    #     for order in self:
    #
    #         order_currency = order.currency_id
    #         ctx = {'date' : order.date_order}
    #
    #         amount_untaxed = amount_tax = 0.0
    #         for line in order.order_line:
    #             amount_untaxed += line.currency_id.with_context(ctx).compute(line.price_subtotal, order_currency)
    #             amount_tax += line.currency_id.with_context(ctx).compute(line.price_tax, order_currency)
    #
    #         order.update({
    #             'amount_untaxed': order.pricelist_id.currency_id.round(amount_untaxed + order.xyz_charges),
    #             'amount_tax': order.pricelist_id.currency_id.round(amount_tax),
    #             'amount_total': amount_untaxed + amount_tax + order.xyz_charges,
    #         })


    # Overridden:
    @api.depends('currency_id')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """
        print ("********************* _amount_all2 ***************************")
        for order in self:
            amount_untaxed = amount_tax = 0.0
            IQamount_untaxed = IQamount_tax = IQamount_total = 0.0

            order_currency = order.currency_id
            ctx = {'date' : order.date_order}

            for line in order.order_line:
                # amount_untaxed += line.price_subtotal
                # amount_tax += line.price_tax

                print (" Currency **", line.currency_id.name, order_currency.name)
                amount_untaxed += line.currency_id.with_context(ctx).compute(line.price_subtotal, order_currency)
                amount_tax += line.currency_id.with_context(ctx).compute(line.price_tax, order_currency)
                print ("amount_untaxed here :", line.price_subtotal, amount_untaxed)


            # amount_untaxed = order.pricelist_id.currency_id.round(amount_untaxed)
            # amount_tax   = order.pricelist_id.currency_id.round(amount_tax)
            amount_untaxed = order.currency_id.round(amount_untaxed)
            amount_tax = order.currency_id.round(amount_tax)
            amount_total = amount_untaxed + amount_tax

            # print ("order.intorder_id", order.intorder_id, order.lead_id)

            if order.intorder_id:
                intOrd = order.intorder_id
                # print ("intOrd.currency_id ", intOrd.currency_id.name, order_currency.name)
                IQamount_untaxed = intOrd.currency_id.with_context(ctx).compute(intOrd.amount_untaxed, order_currency)
                IQamount_taxs = intOrd.currency_id.with_context(ctx).compute(intOrd.amount_tax, order_currency)
                IQamount_total = IQamount_untaxed + IQamount_tax


                print ("iq Currency ** ", intOrd.currency_id.name, order_currency)
                print ("iq untaxAmt here :", intOrd.amount_untaxed, IQamount_untaxed)


            order.update({
                'amount_untaxed': amount_untaxed,
                'amount_tax' : amount_tax,
                'amount_total': amount_total,

                'amount_untaxed1': amount_untaxed,
                'amount_tax1' : amount_tax,
                'amount_total1': amount_total,

                'iq_amount_untaxed': IQamount_untaxed,
                'iq_amount_tax' : IQamount_tax,
                'iq_amount_total': IQamount_total,

                'pl_amount_untaxed': amount_untaxed - IQamount_untaxed,
                'pl_amount_tax' : amount_tax - IQamount_tax,
                'pl_amount_total': amount_total - IQamount_total,
            })


    # Overridden:
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=False, required=True)
    user_id = fields.Many2one('res.users', string='Sales Person', index=True, track_visibility='onchange', default=lambda self: self.env.user)

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sale Order'),
        ('revised', 'Revised'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', track_visibility='always', multi='xyz')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all', track_visibility='always', multi='xyz')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', track_visibility='always', multi='xyz')



    # New:
    lead_id = fields.Many2one('crm.lead', string='Enquiry', ondelete='restrict')
    sale_type = fields.Selection([('quote', 'Customer Quotation'), ('order', 'Sale Order')], string='Order Type',
                                  default='order')

    intorder_id = fields.Many2one('internal.order', string='Internal Order', ondelete='restrict')
    backorder_id = fields.Many2one('sale.order', string='BackOrder', index=True, help="Original CQ mapped against each revised CQs")

    amount_untaxed1 = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', multi="xyz")
    amount_tax1 = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all', multi="xyz")
    amount_total1 = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', multi="xyz")

    iq_amount_untaxed = fields.Monetary(string='IQ Untaxed Amount', store=True, readonly=True, compute='_amount_all', multi="xyz")
    iq_amount_tax = fields.Monetary(string='IQ Taxes', store=True, readonly=True, compute='_amount_all', multi="xyz")
    iq_amount_total = fields.Monetary(string='IQ Total', store=True, readonly=True, compute='_amount_all', multi="xyz")

    pl_amount_untaxed = fields.Monetary(string='Profit/Loss Untaxed Amount', store=True, readonly=True, compute='_amount_all', multi="xyz")
    pl_amount_tax = fields.Monetary(string='Profit/Loss Taxes', store=True, readonly=True, compute='_amount_all', multi="xyz")
    pl_amount_total = fields.Monetary(string='Profit/Loss Total', store=True, readonly=True, compute='_amount_all', multi="xyz")

    project_id = fields.Many2one("account.analytic.account",string='Analytic Account')


    @api.model
    def _generate_Sequence(self, vals):
        cr, context = self._cr, self._context

        refNo = ''

        Company = self.env.user.company_id
        CompCode = (Company.code or Company.name)[:2].upper()

        sale_type = vals.get('sale_type', '')
        if sale_type == 'quote': refNo += 'CQ-'
        else: refNo += 'SO-'

        refNo += CompCode + '-'
        cr.execute(""" select id from sale_order where name ilike '""" + str(refNo) + """%' and backorder_id is null
                     order by to_number(substr(name,(length('""" + str(refNo) + """')+1)),'9999999999')
                     desc limit 1
                 """)
        rec = cr.fetchone()
        if rec:
            case = self.sudo().browse(rec[0])
            auto_gen = case.name[len(refNo) : ]
            refNo = refNo + str(int(auto_gen) + 1).zfill(5)
        else:
            refNo = refNo + '00001'
        return refNo

    @api.multi
    def action_confirm_quote(self):
        """
            Prepares & Creates Sale Order.
        """
        self.ensure_one()

        context = self._context
        SOids = []

        websiteQuote = context.get('websiteQuote', False)

        vals = self.copy_data()
        vals = vals and vals[0] or {}
        vals.update({'origin'     : self.name,
                     'sale_type'  : 'order',
                     })

        newRec = self.create(vals)
        SOids.append(newRec.id)

        print ("websiteQuote", websiteQuote)
        newRec.action_confirm()

        self.write({'state': 'done'})

        if websiteQuote:
            return True

        # action = self.env.ref('sale.action_orders')
        # result = action.read()[0]
        # result['context'] = {}
        #
        # if len(SOids) > 1:
        #     domain = eval(result['domain'])
        #     domain.append(('id', 'in', SOids))
        # else:
        #     res = self.env.ref('sale.view_order_form', False)
        #     result['views'] = [(res and res.id or False, 'form')]
        #     result['res_id'] = SOids and SOids[0] or False


        xml_id = 'action_orders'
        result = self.env.ref('sale.%s' % (xml_id)).read()[0]
        res = self.env.ref('sale.view_order_form', False)
        domain = eval(result['domain'])
        domain.append(('id', 'in', SOids))
        result['domain'] = domain
        result['context'] = {'sale_type': 'order'}

        return result

    # Overridden:
    @api.multi
    def button_dummy(self):
        context = dict(self._context, recompute=True)
        self.with_context(context).write({})
        return True

    # Inherited:
    @api.multi
    def _prepare_invoice(self):
        self.ensure_one()
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals.update({'lead_id' : self.lead_id.id,
                            'intorder_id': self.intorder_id.id
                             })
        return invoice_vals

    # Overridden:
    # TODO:
    # remove if not need, overridden to include currency_id in line, as currency_id is no longer a related
    def _create_delivery_line(self, carrier, price_unit):
        SaleOrderLine = self.env['sale.order.line']

        # Apply fiscal position
        taxes = carrier.product_id.taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
        taxes_ids = taxes.ids
        if self.partner_id and self.fiscal_position_id:
            taxes_ids = self.fiscal_position_id.map_tax(taxes).ids

        # Create the sale order line
        values = {
            'order_id': self.id,
            'name': carrier.name,
            'product_uom_qty': 1,
            'product_uom': carrier.product_id.uom_id.id,
            'product_id': carrier.product_id.id,
            'price_unit': price_unit,
            'tax_id': [(6, 0, taxes_ids)],
            'is_delivery': True,
            'currency_id': self.currency_id.id,
        }
        if self.order_line:
            values['sequence'] = self.order_line[-1].sequence + 1
        sol = SaleOrderLine.create(values)
        return sol

    @api.multi
    def button_mark_Sent(self):
        " Mark as Qtn Mail Sent manually"
        return self.write({'state':'sent'})

    @api.multi
    def action_revised(self):
        self.ensure_one()
        cr, context = self._cr, dict(self._context)

        CallBy = context.get('callby', '')

        vals = self.copy_data()
        vals = vals and vals[0] or {}

        self.write({'state': 'revised'})

        cr.execute("select count(id) from sale_order where \
                    backorder_id is not null and lead_id = %s"%(self.lead_id.id))
        ExistRec = cr.fetchone()
        Cnt = (ExistRec and ExistRec[0] or 0) + 1

        name = str(self.name).split(' - ')
        name = name and name[0] or self.name
        RefNum = str(name) + " - R" + str(Cnt)
        vals.update({'backorder_id': self.id,
                     'name'  : RefNum,
                     'origin': self.origin,
                     })

        newID = self.create(vals)

        if CallBy == 'auto':
            return newID

        domain = [('id', 'in', [newID.id])]

        xml_id = 'action_cust_quote'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        rec_domain = eval(result['domain'])
        rec_domain.append(('id', '=', newID.id))
        result['domain'] = rec_domain
        return result



    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self._generate_Sequence(vals) or 'New'

        return super(SaleOrder, self).create(vals)


    @api.multi
    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        context = dict(self._context)

        if vals.get('state', '') == 'sent':

            for case in self:
                StageID = self.env['crm.stage'].get_StageID('quote_sent')

                if case.sale_type == 'quote' and StageID:
                    ctx = context.copy()
                    ctx.update({'sysCall': True})
                    case.lead_id.with_context(ctx).write({'stage_id': StageID.id})
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'


    @api.depends('product_uom_qty', 'discount_perc', 'discount', 'price_unit', 'tax_id', 'profit_perc', 'profit')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            line.onchange_onAmount()
            # price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            # price += price * ((line.profit_perc or 0.0) / 100.0)
            # price += line.profit
            # taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_id)
            # line.update({
            #     'price_tax': taxes['total_included'] - taxes['total_excluded'],
            #     'price_total': taxes['total_included'],
            #     'price_subtotal': taxes['total_excluded'],
            # })

    # Overridden:
    discount = fields.Float(string='Discount', digits=dp.get_precision('Discount'), default=0.0)
    currency_id = fields.Many2one("res.currency", related=False, string="Currency", readonly=False,
                                  required=True, store=True, default=21)
    # TODO: remove default of currency

    # New:
    discount_perc = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'), default=0.0)
    price_cost = fields.Float(string='Cost', digits=dp.get_precision('Discount'), default=0.0)
    profit_perc = fields.Float(string='Profit (%)', digits=dp.get_precision('Discount'), default=0.0)
    profit = fields.Float(string='Profit', digits=dp.get_precision('Discount'), default=0.0)
    enqline_id = fields.Many2one('pq.enquiry.lines', string='Enquiry Lines', ondelete='restrict')
    target_currency_id = fields.Many2one(related='enqline_id.currency_id', relation='res.currency', store=True, string='Target.Price Currency', readonly=True)
    target_price = fields.Float(related='enqline_id.target_price', string='Target Cost', store=True, readonly=True, digits=dp.get_precision('Product Price'))

    # item_state = fields.Selection([
    #     ('revise', 'Revise'),
    #     ('cancel', 'Cancelled'),
    #     ], string='Customer Feedback', readonly=True, copy=False, index=True)


    @api.multi
    @api.onchange('product_uom_qty', 'discount_perc', 'discount', 'price_unit', 'tax_id', 'profit', 'profit_perc', 'price_cost')
    def onchange_onAmount(self):
        vals = {}
        order = self.order_id
        price = self.price_cost

        profit = self.profit
        discount = self.discount

        if self.profit_perc:
            profit = order.currency_id.round(price * ((self.profit_perc or 0.0) / 100.0))
            vals.update({'profit':profit})

        price += profit

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
        })
        self.update(vals)
        return {}


    # @api.multi
    # def button_toggle_cancel(self):
    #     return self.write({'item_state' : 'cancel'})
    #
    #
    # @api.multi
    # def button_toggle_revise(self):
    #     return self.write({'item_state' : 'revise'})
    #
    # @api.multi
    # def button_toggle_reset(self):
    #     return self.write({'item_state' : False})
