
from odoo import api, fields, models, _
from odoo.exceptions import Warning
from datetime import date, datetime, timedelta


class Accounts(models.Model):
    _inherit = "account.account"

    id_xero = fields.Char('ID Reference of Xero', copy=False)


class Taxes(models.Model):
    _inherit = "account.tax"

    id_xero = fields.Char('ID Reference of Xero', copy=False)


class Payment(models.Model):
    _inherit = "account.payment"

    id_xero = fields.Char('ID Reference of Xero', copy=False)



class Invoice(models.Model):
    _inherit = ['account.invoice']

    # Overridden:
    user_id = fields.Many2one('res.users', string='Sales Person', track_visibility='onchange',
        readonly=True, states={'draft': [('readonly', False)]},
        default=lambda self: self.env.user)

    # New:
    lead_id = fields.Many2one('crm.lead', string='Enquiry', ondelete='restrict')
    intorder_id = fields.Many2one('internal.order', string='Internal Order', ondelete='restrict')
    remarks = fields.Text(string="Remarks")
    id_xero = fields.Char('ID Reference of Xero', copy=False)


    @api.multi
    def action_create_InvNumber(self):
        """
            Method: called from Workflow
            Sets Invoice Number
        """
        cr, uid, context = self._cr, self._uid, dict(self._context or {})
        today = date.today()

        for case in self:
            InvNum = ''
            updatevals = {}

            # allocated number is used for re-validated invoices
            if case.move_name:
                InvNum = case.move_name
            else:
                # Invoice number if internal number is blank
                InvNum = 'INV-'

                CompCode = (case.company_id.code or case.company_id.name)[:2].upper()
                InvNum += CompCode + '-'
                # InvNum += str(today.year) + '-'
                cr.execute(""" select id from account_invoice where move_name ilike '""" + str(InvNum) + """%'  and id != """ + str(case.id) + """
                               order by to_number(substr(move_name,(length('""" + str(InvNum) + """')+1)),'9999999999')
                               desc limit 1""")
                inv_rec = cr.fetchone()
                if inv_rec:
                    inv = self.sudo().browse(inv_rec[0])
                    auto_gen = inv.move_name[len(InvNum) : ]
                    InvNum = InvNum + str(int(auto_gen) + 1).zfill(5)
                else:
                    InvNum = InvNum + '00001'

            updatevals = {'move_name': InvNum, 'number': InvNum}

            # TODO:
            # Check where to update period if exists

            case.write(updatevals)
        return True


    @api.multi
    def action_notify_procurement(self):
        self.ensure_one()

        if not self.intorder_id and self.type != 'out_invoice': return

        user = self.env['res.users'].browse(self._uid)

        groupedRFQ = {}
        for iol in self.intorder_id.order_line:
            key = iol.rfqline_id.order_id

            if not key in groupedRFQ:
                groupedRFQ[key] = [iol.rfqline_id]
            else:
                groupedRFQ[key].append(iol.rfqline_id)


        ProcPartnerIDs = []
        for tu in self.lead_id.team_proc_id.member_ids:
            ProcPartnerIDs.append(tu.partner_id.id)

        subject = 'Re: %s'%(self.lead_id.enq_number)
        body = '<div><span>Following Quotes has been accepted by the Customer for the Enquiry %s.</span></div>'%(self.lead_id.enq_number)

        body += '''\n <table id="rfq_details">
            <tr>
                 <td width="25%" style="text-align:left;">
                     <span><b>RFQ Reference</b></span>
                 </td>
                 <td width="25%" style="text-align:left;">
                     <strong>Vendor</strong>
                 </td>
                 <td width="25%" style="text-align:left;">
                     <strong>Product Code</strong>
                 </td>
                 <td width="25%" style="text-align:left;">
                     <strong>Product Description</strong>
                 </td>
            </tr>
            '''

        for rfq, rfqln in groupedRFQ.items():
            for ln in rfqln:
                body += '''
                <tr>
                     <td width="25%" style="text-align:left;">
                         <span>''' + str(rfq.name) + '''</span>
                     </td>
                     <td width="25%" style="text-align:left;">
                         <span>''' + str(rfq.partner_id.name) + '''</span>
                     </td>
                     <td width="25%" style="text-align:left;">
                         <span>''' + str(ln.product_id.default_code or '') + '''</span>
                     </td>
                     <td width="25%" style="text-align:left;">
                         <span>''' + str(ln.name) + '''</span>
                     </td>
                </tr>
                '''

        body += '</table>'


        # Notify via Mail:
        self.message_post(body=body, subject=subject, message_type='comment',
                    subtype='mail.mt_comment', parent_id=False, attachments=[], partner_ids=ProcPartnerIDs,
                    content_subtype='html')

        return True


    # @api.multi
    # def action_create_po(self):
    #     self.ensure_one()
    #
    #     po_obj = self.env['purchase.order']
    #
    #     if not self.intorder_id and self.type != 'out_invoice': return
    #
    #     groupedRFQ = {}
    #     for iol in self.intorder_id.order_line:
    #         key = iol.rfqline_id.order_id
    #
    #         if not key in groupedRFQ:
    #             groupedRFQ[key] = [iol.rfqline_id]
    #         else:
    #             groupedRFQ[key].append(iol.rfqline_id)
    #
    #
    #     for po, poln in groupedRFQ.items():
    #         povals = po.copy_data()
    #         povals = povals and povals[0] or {}
    #
    #         orderline = []
    #         for ol in poln:
    #             olvals = ol.copy_data()
    #             orderline.append(olvals and olvals[0] or {})
    #
    #         orderline = list(map(lambda x:(0,0,x), orderline))
    #
    #         povals.update({
    #             'order_line': orderline,
    #             'po_type' : 'purchase'
    #             })
    #         po_obj.create(povals)
    #
    #     return True


    @api.multi
    def _get_bank_account(self):
        """
            Fetches Company Bank account
            If exists Bank account In Invoice Currency, then fetches account of same currency,
            else fetched Dollar Account.
        """


    @api.model
    def create(self, vals):
        cr, uid, context = self._cr, self._uid, dict(self._context)
        user = self.env['res.users'].browse(uid)

        if context.get('type', vals.get('type','')) in ('out_invoice', 'in_refund'):
            InvCurrency = self.env['res.currency'].browse(vals.get('currency_id', False))

            cr.execute("""
                select b.id
                from res_partner_bank b
                inner join res_company c on c.id = b.company_id
                where b.company_id = %s and c.partner_id = b.partner_id
                and (b.currency_id = %s or b.by_default is true)
                order by b.by_default desc
                limit 1
            """%(user.company_id.id, InvCurrency.id))
            pbnkid = cr.fetchone()

            vals['partner_bank_id'] = pbnkid and pbnkid[0] or False

        return super(Invoice, self).create(vals)




class InvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    id_xero = fields.Char('ID Reference of Xero', copy=False)
