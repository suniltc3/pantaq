from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.tools import float_is_zero, float_compare, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import Warning
from odoo.tools.safe_eval import safe_eval

from dateutil.relativedelta import relativedelta


class Stage(models.Model):
    _inherit = 'crm.stage'

    stage_type = fields.Selection([('new', 'New'), ('rfq_sent', 'RFQ Sent'), ('io_created', 'IntOrder Created'), ('quote_sent', 'Customer Quote Sent')],
                                  string='Stage Type', help='Set this to action automatically')

    @api.multi
    def get_StageID(self, domain=''):
        res = self.search([('stage_type','=', domain)], order='sequence desc')
        return res and res[0] or False


class Lead(models.Model):
    _inherit = ['crm.lead']
    _rec_name = 'enq_number'
    _order = "priority desc,enq_number desc,date_action,id desc"

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):

        if view_type == 'tree':
            view_id = self.env.ref('Pantaq.pantaq_view_lead_tree').id

        elif view_type == 'form':
            # view_id = self.env.ref('crm.crm_case_form_view_oppor').id
            view_id = self.env.ref('Pantaq.view_crm_enquiry_form').id

        return super(Lead, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)


    @api.one
    @api.depends('purchase_ids')
    def _get_count_records(self):
        nbr = inbr1 = inbr2 = 0
        for order in self.purchase_ids:
            if order.state in ('draft', 'sent') and order.po_type == 'rfq':
                nbr += 1

        for order in self.intorder_ids:
            inbr1 += 1
            if order.state in ('submit', 'done'):
                inbr2 += 1

        self.rfq_count = nbr
        self.intord1_count = inbr1
        self.intord2_count = inbr2


    def _get_msgDomain(self):
        """
            Filter Audit Log/Message Log
            to be hide Customer related record from Purchase User.

        """
        domain = [('model', '=', self._name)]

        PurchaseGrp = self.user_has_groups('purchase.group_purchase_user')
        SalesGrp = self.user_has_groups('sales_team.group_sale_salesman')

        if PurchaseGrp and not SalesGrp:
            domain += ['|', ('is_purchasegroup','=', True), ('force_display','=',True)]

        return domain

    # Overridden:
    message_ids = fields.One2many('mail.message', 'res_id', string='Messages',
                    domain=_get_msgDomain,
                    auto_join=True)
    planned_revenue = fields.Float('Expected Revenue', track_visibility='none')

    # New:
    enq_number = fields.Char(string='Enquiry Number', required=True, readonly=True, index=True, copy=False,
                             default='/')
    enquiry_lines = fields.One2many('pq.enquiry.lines', 'lead_id', string='Lines', readonly=True,
                                    states={'draft': [('readonly', False)]}, copy=True)
    date_created = fields.Date(string='Generated Date', required=True, readonly=True, index=True, copy=False,
                               default=fields.Datetime.now)
    date_received = fields.Date(string='Received Date', required=True, index=True, copy=False,
                                default=fields.Datetime.now, readonly=True,
                                states={'draft': [('readonly', False)]})
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Submitted'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', default='draft')

    team_proc_id = fields.Many2one('crm.team', string='Procurement Team', ondelete='set null',
                           index=True, track_visibility='onchange',
                           help='When sending mails, the default email address is taken from the procurement team.')

    purchase_ids = fields.One2many('purchase.order', 'lead_id', string='Purchase Orders')
    rfq_count = fields.Integer(compute='_get_count_records', string="Number of RFQs", readonly=True)
    assign_id = fields.Many2one('res.users', string='Assigned To', index=True, track_visibility='onchange')

    intorder_ids = fields.One2many('internal.order', 'lead_id', string='Internal Orders')
    intord1_count = fields.Integer(compute='_get_count_records', string="Number of IO", readonly=True)
    intord2_count = fields.Integer(compute='_get_count_records', string="Number of IO - Confirmed", readonly=True)
    next_activity_id = fields.Char("Next Activity")
    title_action = fields.Char("Title Action")
    date_action = fields.Date("Date Action",default=fields.Datetime.now)

    _sql_constraints = [
        ('number_uniq', 'unique(enq_number)', 'Enquiry Number must be unique!'),
    ]


    @api.model
    def default_get(self, fields):
        rec = super(Lead, self).default_get(fields)
        rec.update({
            'type': 'opportunity',
                   })
        return rec

    #Overridden:
    @api.v8
    def _notification_get_recipient_groups(self, message, recipients):
        res = super(crm_lead, self)._notification_get_recipient_groups(message, recipients)
        res['group_sale_salesman'] = []
        return res


    @api.multi
    def button_submit(self):
        """
            Confirm & Submit the Enquiry to Procurement Team
        """
        self.ensure_one()
        cr, uid, context = self._cr, self._uid, dict(self._context)

        for case in self:
            vals = {'state': 'done'}
            if not case.partner_id:
                partner = case._create_lead_partner()
                if partner:
                    vals.update({'partner_id': partner.id})

            if not case.enquiry_lines:
                raise Warning(_("Please add a Product Details to proceed !!"))

            case.write(vals)
            case._send_mail_notify(action='submit')
        return True

    @api.multi
    def button_cancel(self):
        self.ensure_one()
        user = self.env['res.users'].browse(self._uid)

        self._send_mail_notify(action='cancel')

        StageID = self.env.ref('Pantaq.pq_stage_lead9').read()
        StageID = StageID and StageID[0] or {}

        return self.write({'state':'cancel', 'stage_id': StageID.get('id', False)})

    @api.multi
    def button_draft(self):

        StageID = self.env.ref('crm.stage_lead1').read()
        StageID = StageID and StageID[0] or {}

        return self.write({'state':'draft', 'stage_id': StageID.get('id', False)})

    @api.multi
    def button_convert_rfq(self):
        context = dict(self._context)
        self.ensure_one()

        wizid = False
        wiz_obj = self.env['pq.wizard.rfq']
        wizln_obj = self.env['pq.wizard.rfqlines']

        lead_id = self.id

        vals = {'lead_id': lead_id}
        wizid = wiz_obj.create(vals)
        wizid = wizid.id

        self._cr.execute("delete from pq_wizard_rfqlines")

        for ln in self.enquiry_lines:
            lnvals = ln.copy_data()
            lnvals = lnvals and lnvals[0] or {}

            name = ln.name
            if ln.product_id:
                product = ln.product_id
                if product.description_purchase:
                    name += '\n' + product.description_purchase

            lnvals['name'] = name

            lnvals['enqln_id'] = ln.id
            lnvals['lead_id'] = lead_id
            lnvals['wizenq_id'] = wizid
            wizln_obj.create(lnvals)
        xml_id = 'action_enq2rfq_form'
        result = self.env.ref('Pantaq.%s' % (xml_id)).read()[0]
        domain = [('id', '=', wizid)]
        result['domain'] = domain
        return result

    @api.multi
    def _send_mail_notify(self, action='submit'):
        self.ensure_one()

        if not self.team_id.member_ids:
            raise Warning(_("Please map users for the Sales Team [%s] !!"%self.team_id.name))

        if not self.team_proc_id.member_ids:
            raise Warning(_("Please map users for the Procurement Team [%s] !!"%self.team_proc_id.name))

        SalesPartners = list(map(lambda x: x.partner_id.id, self.team_id.member_ids))
        ProcPartners = list(map(lambda x: x.partner_id.id, self.team_proc_id.member_ids))
        NotifyPartners = []

        MsgBody = ''
        force_send = True

        if action == 'submit':
            # template = self.env.ref('Pantaq.email_enquiry_submit')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners]}
            # template.send_mail(self.id, force_send=force_send, email_values=email_values)

            MsgBody = 'Enquiry has been Submitted.'
            NotifyPartners = list(ProcPartners)

        elif action == 'cancel':
            # template = self.env.ref('Pantaq.email_enquiry_cancelled')
            # email_values = {'recipient_ids': [(4, pid) for pid in ProcPartners + SalesPartners]}
            # template.send_mail(self.id, force_send=force_send, email_values=email_values)

            MsgBody = 'Enquiry has been Cancelled.'
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

    @api.model
    def create(self, vals):
        if vals.get('enq_number', '/') == '/':

            vals['enq_number'] = self.env['ir.sequence'].next_by_code('crm.lead') or '/'
        return super(Lead, self).create(vals)


    @api.one
    def _check_Stages(self, vals):
        self.ensure_one()

        Stage = self.env['crm.stage'].browse(vals.get('stage_id', False))

        flag = False
        msg = "Enquiry cannot be marked as '%s'"%(Stage.name)

        if Stage.stage_type == 'rfq_sent' and self.rfq_count == 0:
            flag = True
            msg += ", without the creation of RFQs."

        elif Stage.stage_type == 'io_created' and self.intord1_count == 0:
            flag = True
            msg += ", without receiving any Quotation from Suppliers."

        elif Stage.stage_type == 'quote_sent' and self.sale_number == 0:
            flag = True
            msg += ", without creation of Customer Quotations."

        if flag:
            raise Warning(_(msg))

        return True

    @api.multi
    def write(self, vals):
        cr, context = self._cr, self._context
        sysCall = context.get('sysCall', False)

        if 'stage_id' in vals and not sysCall:
            self._check_Stages(vals)
        return super(Lead, self).write(vals)



class EnquiryLines(models.Model):
    _name = 'pq.enquiry.lines'
    _description = 'Enquiry Lines'

    def _get_default_uom_id(self):
        return self.env["product.uom"].search([], limit=1, order='id').id


    lead_id = fields.Many2one('crm.lead', string='Enquiry', required=True, ondelete='cascade', index=True, copy=False)
    name = fields.Text(string='Description', required=True)

    product_id = fields.Many2one('product.product', string='Product', domain=[('sale_ok', '=', True)], change_default=True, ondelete='restrict')
    product_uom_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True, default=1.0)
    product_uom = fields.Many2one('product.uom', string='Unit of Measure', required=True,
                                      default=_get_default_uom_id)
    # procurement_ids = fields.One2many('procurement.order', 'enqline_id', string='Procurements')

    has_targetprice = fields.Boolean('I have Target Price')
    target_price = fields.Float('Target Price', help="Enter Target Price for a unit.")
    currency_id = fields.Many2one('res.currency', 'Currency', help="Select Currency for the Target Price",
                    default=lambda self: self.env.user.company_id.currency_id)
    partner_ids = fields.Many2many('res.partner', string='Suppliers', domain=[('supplier', '=', True)])


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
        # With price then bring pricelist of product same as sale

        name = product.name_get()[0][1]

        if product.description_sale:
            name += '\n' + product.description_sale
        vals['name'] = name

        self.update(vals)
        return {'domain': domain}



class Team(models.Model):
    _inherit = ['crm.team']

    category = fields.Selection([
        ('sales', 'Sales'),
        ('procurement', 'Procurement'),
        ], string='Team Category', required=True, copy=False, index=True, track_visibility='onchange', default='sales')


    #overridden:
    @api.model
    def action_your_pipeline(self):
        action = self.env.ref('crm.crm_lead_opportunities_tree_view').read()[0]
        user_team_id = self.env.user.sale_team_id.id
        PurchaseGrp = self.user_has_groups('purchase.group_purchase_user')

        if not user_team_id:
            user_team_id = self.search([], limit=1).id
            action['help'] = """<p class='oe_view_nocontent_create'>Click here to add new opportunities</p><p>
    Looks like you are not a member of a sales team. You should add yourself
    as a member of one of the sales team.
</p>"""
            if user_team_id:
                action['help'] += "<p>As you don't belong to any sales team, Odoo opens the first one by default.</p>"

        action_context = safe_eval(action['context'], {'uid': self.env.uid})
        action_domain = safe_eval(action['domain'])

        if user_team_id:
            action_context['default_team_id'] = user_team_id

        if PurchaseGrp:
            action_context.update({
                'search_default_assigned_to_me': 0,
                'search_default_team_id': 0,
            })
            action_domain.append(('state', '!=', 'draft'))

        tree_view_id = self.env.ref('crm.crm_case_tree_view_oppor').id
        form_view_id = self.env.ref('crm.crm_case_form_view_oppor').id
        kanb_view_id = self.env.ref('crm.crm_case_kanban_view_leads').id
        # action['views'] = [
        #         [kanb_view_id, 'kanban'],
        #         [tree_view_id, 'tree'],
        #         [form_view_id, 'form'],
        #         [False, 'graph'],
        #         [False, 'calendar'],
        #         [False, 'pivot']
        #     ]
        # action['context'] = action_context
        action.update({
            'views': [
                [kanb_view_id, 'kanban'],
                [tree_view_id, 'tree'],
                [form_view_id, 'form'],
                [False, 'graph'],
                [False, 'calendar'],
                [False, 'pivot']
            ],
            'context': action_context,
            'domain' : action_domain,
        })
        return action



# class Procurement(models.Model):
#     _inherit = ['procurement.order']
#
#     # Overriden:
#     product_id = fields.Many2one('product.product', 'Product',
#         readonly=True, required=False,
#         states={'confirmed': [('readonly', False)]})
#
#     # New:
#     enqline_id   = fields.Many2one('pq.enquiry.lines', string='Enquiry Lines', ondelete='cascade')
#     lead_id      = fields.Many2one('crm.lead', string='Enquiry', ondelete='cascade')
#     target_price = fields.Float('Targeted Price')
#     currency_id  = fields.Many2one('res.currency', 'Currency')
#     partner_ids  = fields.Many2many('res.partner', string='Supplier', domain=[('supplier', '=', True)])
#
#
#     # Inherited: from procurement
#     def _find_suitable_rule(self):
#         rule_id = super(Procurement, self)._find_suitable_rule()
#         if not rule_id:
#             rule_id = self.env['procurement.rule'].browse(5) # Todo: Rule
#         return rule_id
#
#      # Overridden: from Purchase
#     @api.multi
#     def _run(self):
#         return self.make_po()
#
#     # Overridden: from Purchase
#     @api.multi
#     def make_po(self):
#         cache = {}
#         res = []
#
#         for procurement in self:
#             EnquiryRec = procurement.lead_id
#             suppliers = procurement.partner_ids
#
#             if not suppliers:
#                 procurement.message_post(body=_('No vendor associated to product %s. Please set one to fix this procurement.') % (procurement.product_id.name))
#                 continue
#
#             gpo = procurement.rule_id.group_propagation_option
#             group = (gpo == 'fixed' and procurement.rule_id.group_id) or \
#                     (gpo == 'propagate' and procurement.group_id) or False
#
#             # Create RFQs for all Suppliers
#             for supplier in suppliers:
#                 partner = supplier
#
#                 domain = (
#                     ('partner_id', '=', partner.id),
#                     ('state', '=', 'draft'),
#                     ('company_id', '=', procurement.company_id.id),
#                     ('lead_id', '=', EnquiryRec.id),
#                     ('po_type', '=', 'rfq'),
#                     ('origin', '=', EnquiryRec and EnquiryRec.enq_number or procurement.origin)
#                 )
#
#                 if domain in cache:
#                     po = cache[domain]
#                 else:
#                     po = self.env['purchase.order'].search([dom for dom in domain])
#                     po = po[0] if po else False
#                     cache[domain] = po
#
#                 if not po:
#                     vals = procurement._prepare_purchase_order(partner)
#                     vals['po_type'] = 'rfq'
#                     vals['lead_id'] = EnquiryRec.id
#                     po = self.env['purchase.order'].create(vals)
#                     cache[domain] = po
#
#                 elif not po.origin or procurement.origin not in po.origin.split(', '):
#                     # Keep track of all procurements
#                     if po.origin:
#                         if procurement.origin:
#                             po.write({'origin': po.origin + ', ' + procurement.origin})
#                         else:
#                             po.write({'origin': po.origin})
#                     else:
#                         po.write({'origin': procurement.origin})
#
#                 if po:
#                     res += [procurement.id]
#
#                 # Create Line
#                 po_line = False
#                 for line in po.order_line:
#
#                     if line.product_id == procurement.product_id and line.name == procurement.name:
#                         if procurement.product_id and line.product_uom != procurement.product_id.uom_po_id:
#                             continue
#
#                         procurement_uom_po_qty = procurement.product_qty
#
#                         if procurement.product_id:
#                             procurement_uom_po_qty = procurement.product_uom._compute_quantity(procurement.product_qty, procurement.product_id.uom_po_id)
#
#                         po_line = line.write({
#                             'product_qty': line.product_qty + procurement_uom_po_qty,
#                             'procurement_ids': [(4, procurement.id)]
#                         })
#                         break
#
#                 if not po_line:
#                     vals = procurement._prepare_purchase_order_line(po, supplier)
#                     vals['target_price'] = procurement.target_price
#                     self.env['purchase.order.line'].create(vals)
#         return res


    # Overridden
    @api.multi
    def _prepare_purchase_order_line(self, po, supplier):
        self.ensure_one()

        seller, taxes, taxes_list = False, [], []
        print ("seld", self)
        procurement_uom_po_qty = self.product_qty
        product_uom = self.product_uom.id

        if self.product_id:
            procurement_uom_po_qty = self.product_uom._compute_quantity(self.product_qty, self.product_id.uom_po_id)
            taxes = self.product_id.supplier_taxes_id
            product_uom = self.product_id.uom_po_id.id

        fpos = po.fiscal_position_id
        taxes_id = fpos.map_tax(taxes) if fpos else taxes
        if taxes_id:
            taxes_id = taxes_id.filtered(lambda x: x.company_id.id == self.company_id.id)
            taxes_list = taxes_id.ids

        name = self.name

        date_planned = self.env['purchase.order.line']._get_date_planned(seller, po=po).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        return {
            'name': name,
            'product_qty': procurement_uom_po_qty,
            'product_id': self.product_id.id,
            'product_uom': product_uom,
            'price_unit': 0.00,
            'date_planned': date_planned,
            'taxes_id': [(6, 0, taxes_list)],
            'procurement_ids': [(4, self.id)],
            'order_id': po.id,
            'enqline_id': self.enqline_id.id,
        }


    # Overridden:
    def _get_purchase_order_date(self, schedule_date):
        """Return the datetime value to use as Order Date (``date_order``) for the
           Purchase Order created to satisfy the given procurement. """
        self.ensure_one()
        seller_delay = 0
        if self.product_id:
            seller_delay = int(self.product_id._select_seller().delay)
        return schedule_date - relativedelta(days=seller_delay)

