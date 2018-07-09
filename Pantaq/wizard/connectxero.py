
from odoo import api, fields, models, _
import datetime
import logging

from odoo.addons.Pantaq.apixero import xeroAuth
myxero = xeroAuth.MyXero()

_logger = logging.getLogger(__name__)


class ConnectXero(models.TransientModel):
    _name = "wiz.connect.xero"

    name = fields.Char('Name', default='Odoo-Xero Integration')


    @api.one
    def _map_accountTypes(self):
        '''
            Map Xero Account Type in Odoo
        '''

        AccDict, OXDict = {}, {}
        AccTypes = self.env['account.account.type'].search_read([], ['name'])

        for a in AccTypes:
            AccDict[a['name']] = a['id']

        for key, val in AccDict.iteritems():
            # Assets:
            if key == 'Current Assets':
                OXDict['CURRENT ASSET'] = val
                OXDict['INVENTORY ASSET'] = val

            elif key == 'Fixed Assets':
                OXDict['FIXED ASSET'] = val

            elif key == 'Non-current Assets':
                OXDict['NONCURRENT ASSET'] = val

            elif key == 'Prepayments':
                OXDict['PREPAYMENT ASSET'] = val

            # Liabilities:
            elif key == 'Current Liabilities':
                OXDict['CURRLIAB LIABILITY'] = val

            elif key == 'Non-current Liabilities':
                OXDict['LIABILITY LIABILITY'] = val
                OXDict['TERMLIAB LIABILITY'] = val

            # Equity:
            elif key == 'Equity':
                OXDict['EQUITY EQUITY'] = val

            # Expense:
            elif key == 'Depreciation':
                OXDict['DEPRECIATN EXPENSE'] = val

            elif key == 'Cost of Revenue':
                OXDict['DIRECTCOSTS EXPENSE'] = val

            elif key == 'Expenses':
                OXDict['OVERHEADS EXPENSE'] = val
                OXDict['EXPENSE EXPENSE'] = val

            # Revenue:
            elif key == 'Income':
                OXDict['REVENUE REVENUE'] = val
                OXDict['SALES REVENUE'] = val

            elif key == 'Other Income':
                OXDict['OTHERINCOME REVENUE'] = val

        return OXDict

    def action_import_contacts(self):

        Partner = self.env['res.partner']
        History = self.env['pantaq.xero.history']

        LastRun = False
        xCids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_contacts')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        result, logMsg, eflag = myxero.getContacts(LastRun=LastRun)

        for rs in result:
            xCids.append(rs.get('ContactID', ''))

        # Existing: Map Odoo-Xero Contacts
        for r in Partner.search_read([('id_xero','in', xCids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in result:
            xID = rs.get('ContactID', '')
            vals = self._prepare_partner_data(rs)[0]

            if xID in xODict.keys():
                Partner.browse(xODict[xID]).write(vals)
            else:
                Partner.create(vals)

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_contacts'})


        # ----------------------------------------------------------------
        # TODO Fixme: Following fields were not found in Result
        #       Check whether they are available with Private Connection
        #
        #   * Website
        #   * Bank details? Account number
        #   * VAT & Currency
        #   * Sub/child Contacts
        # ----------------------------------------------------------------
        return True

    def action_export_contacts(self):
        context = dict(self._context)

        Partner = self.env['res.partner']
        History = self.env['pantaq.xero.history']

        LastRun = False
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'export_contacts')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        GivenRec = context.get('partnerID', False)
        if GivenRec:
            domain = [('id','=', GivenRec)]
        else:
            domain = [('write_date','>=', LastRun)]

        partners = Partner.search(domain)
        NewVals, SaveVals = {}, {}

        for p in partners:
            if p.id_xero:
                SaveVals[p.id_xero] = {'Name': p.name}
            else:
                NewVals[p] = {'Name': p.name}

        # TODO:
        # prepare vals to export

        oxMapIds, logMsg, eflag = myxero.putContacts(NewData=NewVals, SaveData=SaveVals)

        # Update XeroID into Odoo
        for part, v in oxMapIds.iteritems():
            part.write({'id_xero': v})

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)

        elif not GivenRec:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(NewVals.keys() + SaveVals.keys())),
                        'date_run': now,
                        'type': 'export_contacts'})
        return True


    def action_import_invoices(self):

        Invoice = self.env['account.invoice']
        History = self.env['pantaq.xero.history']
        Partner = self.env['res.partner']

        LastRun = False
        xOids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_invoices')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        result, logMsg, eflag = myxero.getInvoices(LastRun=LastRun)

        for rs in result:
            xOids.append(rs.get('InvoiceID', ''))

        # Existing: Map Odoo-Xero Records
        for r in Invoice.search_read([('id_xero','in', xOids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in result:
            xID = rs.get('InvoiceID', '')
            status = rs.get('Status', {})

            # Get: Complete Data
            resData, l, e = myxero.getInvoices(RecordID=xID)
            resData = resData and resData[0] or {}

            if xID in xODict.keys():
                inv = Invoice.browse(xODict[xID])

                if inv.state == 'draft':
                    vals = self._prepare_invoice_data(resData)[0]
                    inv.write(vals)
                    self._create_invoiceline(resData.get('LineItems', []), inv)

                # elif inv.state == 'paid':
                #     continue
            else:
                vals = self._prepare_invoice_data(resData)[0]
                inv = Invoice.create(vals)
                self._create_invoiceline(resData.get('LineItems', []), inv)

            inv.compute_taxes()

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #  Validate
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            if status in ('AUTHORISED', 'PAID') and inv.state == 'draft':
                inv.action_invoice_open()

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #  Payments
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            if rs.get('Payments', []):
                self._create_vouchers(rs.get('Payments', []), inv)

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #  Refunds:
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            if rs.get('CreditNotes', []):
                self._create_invoiceRefund(rs.get('CreditNotes', []), inv)


        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_invoices'})
        return True


    def action_export_invoices(self):
        context = dict(self._context)

        Invoice = self.env['account.invoice']
        History = self.env['pantaq.xero.history']

        LastRun = False
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'export_invoices')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        GivenRecs = context.get('invoiceIds', [])
        if GivenRecs:
            domain = [('id','in', GivenRecs), ('id_xero', '=', None)]
        else:
            # Export only New/Draft Invoices
            domain = [('create_date','>=', LastRun), ('id_xero', '=', None)]

        invoices = Invoice.search(domain)
        NewVals = self._prepare_xeroInvoice_data(invoices)

        oxMapIds, logMsg, eflag = myxero.putInvoices(NewData=NewVals)

        # Update XeroID into Odoo
        for inv, v in oxMapIds.iteritems():
            inv.write({'id_xero': v.get('id_xero',''),
                       'move_name': v.get('number', '')})
            if inv.state == 'draft':
                inv.action_invoice_proforma2()

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)

        elif not GivenRecs:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(NewVals.keys())),
                        'date_run': now,
                        'type': 'export_invoices'})

        return True


    def action_import_products(self):

        Product = self.env['product.product']
        History = self.env['pantaq.xero.history']

        LastRun = False
        xCids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_products')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        result, logMsg, eflag = myxero.getProducts(LastRun=LastRun)

        for rs in result:
            xCids.append(rs.get('ItemID', ''))

        # Existing: Map Odoo-Xero Records
        for r in Product.search_read([('id_xero','in', xCids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in result:
            xID = rs.get('ItemID', '')
            vals = self._prepare_product_data(rs)[0]

            if xID in xODict.keys():
                Product.browse(xODict[xID]).write(vals)
            else:
                Product.create(vals)

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_products'})

        return True


    def action_export_products(self):
        context = dict(self._context)

        Product = self.env['product.product']
        History = self.env['pantaq.xero.history']

        LastRun = False
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'export_products')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        GivenRec = context.get('productID', False)
        if GivenRec:
            domain = [('id','=', GivenRec)]
        else:
            domain = [('write_date','>=', LastRun)]

        products = Product.search(domain)
        NewVals, SaveVals = {}, {}

        for p in products:
            if p.id_xero:
                SaveVals[p.id_xero] = {'Name': p.name, 'Code': p.default_code or p.name}
            else:
                NewVals[p] = {'Name': p.name, 'Code': p.default_code or p.name}

        # TODO:
        # prepare vals to export

        oxMapIds, logMsg, eflag = myxero.putProducts(NewData=NewVals, SaveData=SaveVals)

        # Update XeroID into Odoo
        for prod, v in oxMapIds.iteritems():
            prod.write({'id_xero': v})

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)

        elif not GivenRec:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(NewVals.keys() + SaveVals.keys())),
                        'date_run': now,
                        'type': 'export_products'})
        return True



    def action_import_accounts(self):
        '''
            Import Accounts from Xero
        '''

        Account = self.env['account.account']
        History = self.env['pantaq.xero.history']

        LastRun = False
        xCids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_accounts')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        AccTypeDict = self._map_accountTypes()[0]

        result, logMsg, eflag = myxero.getAccounts(LastRun=LastRun)

        for rs in result:
            xCids.append(rs.get('AccountID', ''))

        # Existing: Map Odoo-Xero Records
        for r in Account.search_read([('id_xero','in', xCids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in result:
            xID = rs.get('AccountID', '')
            vals = self._prepare_account_data(rs, AccTypeDict=AccTypeDict)[0]

            if xID in xODict.keys():
                Account.browse(xODict[xID]).write(vals)
            else:
                Account.create(vals)

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_accounts'})

        return True


    def action_import_taxes(self):
        '''
            Import Taxes from Xero
        '''

        Tax = self.env['account.tax']
        History = self.env['pantaq.xero.history']

        LastRun = False
        xCids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_taxes')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)

        result, logMsg, eflag = myxero.getTaxes(LastRun=LastRun)

        for rs in result:
            xCids.append(rs.get('TaxType', ''))

        # Existing: Map Odoo-Xero Records
        for r in Tax.search_read([('id_xero','in', xCids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in result:
            xID = rs.get('TaxType', '')
            vals = self._prepare_tax_data(rs)[0]

            if xID in xODict.keys():
                Tax.browse(xODict[xID]).write(vals)
            else:
                Tax.create(vals)

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_taxes'})

        return True


    def action_import_payments(self):
        '''
            Import Payments from Xero
        '''

        Payment = self.env['account.payment']
        History = self.env['pantaq.xero.history']

        LastRun = False
        xCids, xODict = [], {}
        now = datetime.datetime.now()

        runDt = History.search_read([('type','=', 'import_payments')], ['date_run'], limit=1)
        runDt = runDt and runDt[0]['date_run'] or ''
        LastRun = fields.Datetime.from_string(runDt)


        result, logMsg, eflag = myxero.getPayments(LastRun=LastRun)
        self._create_vouchers(result)

        if eflag:
            _logger.warning('Xero Error: %s'%logMsg)
        else:
            History.create({'name': '%s : %s record(s)'%(logMsg, len(result)) , 'date_run': now,
                        'type': 'import_payments'})

        return True

    @api.one
    def _prepare_partner_data(self, data):
        res = {
            'id_xero': data.get('ContactID', ''),
            'name' : data.get('Name', ''),
            'email': data.get('EmailAddress', ''),
            'supplier': data.get('IsSupplier', False),
            'customer': data.get('IsCustomer', False),
            'active' : True if data.get('ContactStatus', '') == 'ACTIVE' else False,
        }

        for ph in data.get('Phones', []):
            num = ph.get('PhoneCountryCode', '') + ph.get('PhoneAreaCode', '') + ph.get('PhoneNumber', '')

            if ph.get('PhoneType', '') == 'MOBILE': res['mobile'] = num
            elif ph.get('PhoneType', '') == 'DEFAULT': res['phone'] = num
            elif ph.get('PhoneType', '') == 'FAX': res['fax'] = num

        for adr in data.get('Addresses', []):
            if adr.get('AddressType', '') != 'POBOX':
                continue
            country = adr.get('Country', '')
            region = adr.get('Region', '')
            countryID = stateID = False

            if country:
                Country = self.env['res.country'].search([('name', '=', country)])
                countryID = Country and Country[0].id or False

            if region:
                State = self.env['res.country.state'].search([('name', '=', region)])
                stateID = State and State[0].id or False

                if not stateID and countryID:
                    self.env['res.country'].create({'name': region, 'code': region[:2],
                                                    'country_id': countryID})

            res.update({
                'street': adr.get('AddressLine1', '') + ' ' + adr.get('AddressLine2', ''),
                'street2': adr.get('AddressLine3', '') + ' ' + adr.get('AddressLine4', ''),
                'city' : adr.get('City', ''),
                'zip': adr.get('PostalCode', ''),
                'country_id': countryID,
                'state_id': stateID,
            })

        return res

    @api.one
    def fetch_Partner(self, IdXero=False):
        '''
            Fetch Partner from Odoo Master,
            If None found create it
        '''
        obj = self.env['res.partner']
        if not IdXero:
            return obj

        rec = obj.search([('id_xero', '=', IdXero)])
        Partner = rec and rec[0] or obj

        if not Partner:
            Res, l, e = myxero.getContacts(RecordID=IdXero)
            vals = self._prepare_partner_data(Res[0])[0]
            Partner = obj.create(vals)
        return Partner

    @api.one
    def _create_vouchers(self, data, invoice=False):
        Payment = self.env['account.payment']

        xOids, xODict = [], {}

        for rs in data:
            xOids.append(rs.get('PaymentID', ''))

        # Existing: Map Odoo-Xero Records
        for r in Payment.search_read([('id_xero','in', xOids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for d in data:
            xID = d.get('PaymentID', '')

            # Get: Complete Data
            resData, l, e = myxero.getPayments(RecordID=xID)
            resData = resData and resData[0] or {}

            if xID in xODict.keys():
                pay = Payment.browse(xODict[xID])

                if pay.state == 'draft':
                    vals = self._prepare_payments_data(resData, invoice)[0]
                    Payment.write(vals)

                elif pay.state == 'posted':
                    continue
            else:
                vals = self._prepare_payments_data(resData, invoice)[0]
                ctx = {}
                if invoice:
                    ctx = {'default_invoice_ids': [(4, invoice.id)]}
                pay = Payment.with_context(ctx).create(vals)

            if resData.get('Status', '') == 'AUTHORISED':
                pay.post()
        return True

    @api.one
    def _create_invoiceRefund(self, data, invoice):

        Invoice = self.env['account.invoice']

        xOids, xODict = [], {}
        eflag = False

        for rs in data:
            xOids.append(rs.get('ID', ''))

        # Existing: Map Odoo-Xero Records
        for r in Invoice.search_read([('id_xero','in', xOids)], ['id_xero']):
            xODict[r['id_xero']] = r['id']

        for rs in data:
            xID = rs.get('ID', '')

            # Get: Complete Data
            resData, l, eflag = myxero.getCreditNotes(RecordID=xID)
            resData = resData and resData[0] or {}
            status = resData.get('Status', {})

            if xID in xODict.keys():
                inv = Invoice.browse(xODict[xID])

                if inv.state == 'draft':
                    vals = self._prepare_invoice_data(resData)[0]
                    inv.write(vals)
                    self._create_invoiceline(resData.get('LineItems', []), inv)

                # elif inv.state == 'paid':
                #     continue
            else:
                vals = self._prepare_invoice_data(resData)[0]
                inv = Invoice.create(vals)
                self._create_invoiceline(resData.get('LineItems', []), inv)

            inv.compute_taxes()

            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #  Validate
            # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            if status in ('AUTHORISED', 'PAID') and inv.state == 'draft':
                inv.action_invoice_open()

            # # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # #  Allocations
            # # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # if rs.get('Allocations', []):
            #     self._create_vouchers(rs.get('Payments', []), inv)
            #

            if eflag:
                _logger.warning('Xero Error: %s'%logMsg)

        return True


    @api.one
    def _prepare_invoice_data(self, data):
        context = dict(self._context)

        Invoice = self.env['account.invoice']
        contact = data.get('Contact', {}).get('ContactID', '')

        Partner = self.fetch_Partner(data.get('Contact', {}).get('ContactID', ''))[0]
        status = data.get('Status', {})
        reference = data.get('Reference', '')

        type = id_xero = number = ''
        if data.get('Type', {}) == 'ACCREC': # Customer Invoice
            type = 'out_invoice'
            id_xero = data.get('InvoiceID', '')
            number = data.get('InvoiceNumber', '')

        elif data.get('Type', {}) == 'ACCPAY': # Supplier Invoice
            type = 'in_invoice'
            id_xero = data.get('InvoiceID', '')
            reference = data.get('InvoiceNumber', '')

        elif data.get('Type', {}) == 'ACCRECCREDIT': # Credit Note
            type = 'out_refund'
            id_xero = data.get('CreditNoteID', '')
            number = data.get('CreditNoteNumber', '')

        elif data.get('Type', {}) == 'ACCPAYCREDIT': # Debit Note
            type = 'in_refund'
            id_xero = data.get('CreditNoteID', '')
            reference = data.get('CreditNoteNumber', '')

        ctx2 = context.copy()
        ctx2.update({'type': type})
        res = Invoice.with_context(ctx2).default_get(['currency_id', 'company_id', 'journal_id'])

        InvDate = data.get('Date', fields.Datetime.now())

        # TODO: FIXME
        # .. Fetch Invoice Company
        Company = self.env.user.with_env(self.env).company_id

        ctx = context.copy()
        ctx.update({'date': InvDate})
        Currency = self.with_context(ctx).fetch_Currency(InvCurrencyCode=data.get('CurrencyCode', ''),
                                                        DefCurrencyCode=data.get('DefaultCurrency', ''),
                                                        Rate=data.get('CurrencyRate', 0),
                                                        EffDate=InvDate, Company=Company)[0]

        if type in ('out_invoice', 'out_refund'):
            account_id = Partner.property_account_receivable_id.id
        else:
            account_id = Partner.property_account_payable_id.id

        res.update({
            'id_xero': id_xero,
            'partner_id': Partner.id,
            'account_id': account_id,
            'fiscal_position_id': Partner.property_account_position_id.id,
            'origin':  reference,
            'name'  :  reference,
            'date_invoice': InvDate,
            'date_due': data.get('DueDate', False),
            'type': type,
            'currency_id': Currency.id,
        })

        if number:
            # Vendor Bills: No Unique Numbering
            res['move_name'] = number

        return res


    @api.one
    def _create_invoiceline(self, data, invoice):
        InvoiceLine = self.env['account.invoice.line']

        def _prepare_vals(rs, xID):
            prod = self.fetch_Product(Code=rs.get('ItemCode', ''))[0]
            acc = self.fetch_Account(Code=rs.get('AccountCode', ''))[0]

            taxes = []
            Tax = self.fetch_Tax(rs.get('TaxType', ''))
            if Tax and Tax[0]: taxes = [(6, 0, [Tax[0].id])]

            iline = InvoiceLine.new({
                'product_id': prod.id,
                'price_unit': rs.get('UnitAmount', 0.0),
                'invoice_id': invoice.id,
            })
            iline._onchange_product_id()
            vals = iline._convert_to_write({name: iline[name] for name in iline._cache})
            vals.update({
                'id_xero': xID,
                'product_id': prod.id,
                'name': rs.get('Description', ''),
                'quantity': rs.get('Quantity', 1.0),
                'price_unit': rs.get('UnitAmount', 0.0),
                'account_id': acc.id,
                'invoice_line_tax_ids': taxes,
            })
            lines.append(vals)
            return vals

        lines = []
        self._cr.execute("delete from account_invoice_line where invoice_id = '%s'"%(invoice.id))

        for ln in data:
            # TODO: FIXME
            # Credit Note: LineItems, ID references are not present
            xID = ln.get('LineItemID', '')
            if xID:
                self._cr.execute("delete from account_invoice_line where id_xero = '%s'"%(xID))
            vals = _prepare_vals(ln, xID)

        lines = list(map(lambda x: (0, 0, x), lines ))
        invoice.write({'invoice_line_ids': lines})

        return True


    @api.one
    def _prepare_payments_data(self, data, invoice=False):
        Payment = self.env['account.payment']
        Journal = self.env['account.journal']

        Partner = self.fetch_Partner(data.get('Invoice',{}).get('Contact', {}).get('ContactID', ''))[0]

        jdomain = [('type','=','bank'), ('currency_id', '=', None)]
        if invoice:
            jdomain += [('company_id','=', invoice.company_id.id)]

        journal = Journal.search(jdomain)
        currency = journal.currency_id

        payType = 'inbound'
        if data.get('PaymentType', '') == 'ACCPAYPAYMENT':
            payType = 'outbound'
        # TODO: Check refund payments

        payment_methods = journal.inbound_payment_method_ids if payType == 'inbound' else journal.outbound_payment_method_ids

        res = {
            'id_xero': data.get('PaymentID', ''),
            'payment_type': payType,
            'partner_type': 'customer',
            'partner_id': Partner.id,
            'journal_id': journal.id,
            'communication': data.get('Reference', ''),
            'payment_date': data.get('Date', False),
            'amount': data.get('Amount', 0),

            'payment_method_id': payment_methods and payment_methods[0].id or False,
        }

        return res

    @api.one
    def _prepare_product_data(self, data):

        Suptaxes, Custaxes = [], []
        Tax = self.fetch_Tax(data.get('SalesDetails', {}).get('TaxType', ''))
        if Tax and Tax[0]:
            Custaxes = [(6, 0, [Tax[0].id])]

        Tax = self.fetch_Tax(data.get('PurchaseDetails', {}).get('TaxType', ''))
        if Tax and Tax[0]:
            Suptaxes = [(6, 0, [Tax[0].id])]

        IncAcc = self.fetch_Account(Code=data.get('SalesDetails', {}).get('AccountCode', ''))[0]
        ExpAcc = self.fetch_Account(Code=data.get('PurchaseDetails', {}).get('AccountCode', ''))[0]

        SalePrice = data.get('SalesDetails', {}).get('UnitPrice', 0)
        CostPrice = data.get('PurchaseDetails', {}).get('UnitPrice', 0)

        res = {
            'id_xero': data.get('ItemID', ''),
            'name' : data.get('Name', ''),
            'default_code': data.get('Code', ''),
            'description_sale': data.get('Description', ''),
            'description_purchase': data.get('PurchaseDescription', ''),
            'taxes_id': Custaxes,
            'supplier_taxes_id': Suptaxes,
            'property_account_income_id': IncAcc.id,
            'property_account_expense_id': ExpAcc.id,
            'list_price': SalePrice,
            'standard_price': CostPrice,
            'sale_ok': data.get('IsSold', False),
            'purchase_ok': data.get('IsPurchased', False),
        }
        return res

    @api.one
    def fetch_Product(self, IdXero=False, Code=False):
        '''
            Fetch Product from Odoo Master,
            If None found create it
        '''
        obj = self.env['product.product']

        if not IdXero and not Code:
            return obj

        Res = []
        if Code and not IdXero:
            Res, l, e = myxero.getProducts(RecordID=Code)
            IdXero = Res and Res[0].get('ItemID', '') or False

        product = obj.search([('id_xero', '=', IdXero)])
        Product = product and product[0] or obj

        if not Product:
            if not Res:
                Res, l, e = myxero.getProducts(RecordID=IdXero)
            vals = self._prepare_product_data(Res[0])[0]
            Product = obj.create(vals)

        return Product


    @api.one
    def _prepare_account_data(self, data, AccTypeDict={}):
        if not AccTypeDict:
            AccTypeDict = self._map_accountTypes()[0]

        TypID = AccTypeDict.get('%s %s'%(data.get('Type', ''), data.get('Class', '')), False)

        taxes = []
        Tax = self.fetch_Tax(data.get('TaxType', ''))
        if Tax and Tax[0]: taxes = [(6, 0, [Tax[0].id])]

        res = {
            'id_xero': data.get('AccountID', ''),
            'code': data.get('Code', ''),
            'name' : data.get('Name', ''),
            'user_type_id': TypID,
            'tax_ids': taxes,
        }
        return res

    @api.one
    def fetch_Account(self, IdXero=False, Code=False):
        '''
            Fetch Account from Odoo Master,
            If None found create it
        '''
        obj = self.env['account.account']

        if not IdXero and not Code:
            return obj

        Res = []
        if Code and not IdXero:
            Res, l, e = myxero.getAccounts(RecordID=Code)
            IdXero = Res and Res[0].get('AccountID', '') or False

        rec = obj.search([('id_xero', '=', IdXero)])
        Account = rec and rec[0] or obj

        if not Account:
            if not Res:
                Res, l, e = myxero.getAccounts(RecordID=IdXero)
            vals = self._prepare_account_data(Res[0])[0]
            Account = obj.create(vals)
        return Account


    @api.one
    def _prepare_tax_data(self, data):

        typ = 'sale'

        Exp = data.get('CanApplyToExpenses', False)
        Rev = data.get('CanApplyToRevenue', False)

        if Exp: typ = 'purchase'
        elif not Exp and not Rev: typ = 'none'

        res = {
            'id_xero': data.get('TaxType', ''),
            'name' : data.get('Name', ''),
            'type_tax_use': typ,
            'amount': data.get('EffectiveRate', 0),
        }
        return res


    @api.one
    def fetch_Tax(self, IdXero=False):
        '''
            Fetch Tax from Odoo Master,
            If None found create it

        '''
        obj = self.env['account.tax']
        if not IdXero: return obj

        # Tax Code to be considered as ID
        tax = obj.search([('id_xero', '=', IdXero)])
        Tax = tax and tax[0] or obj

        if not Tax:
            Res, l, e = myxero.getTaxes(RecordID=IdXero)
            vals = self._prepare_tax_data(Res[0])[0]
            Tax = obj.create(vals)
        return Tax


    @api.one
    def fetch_Currency(self, InvCurrencyCode=False, DefCurrencyCode=False, Rate=0, EffDate=False, Company=False):
        '''
            Fetch Currency from Odoo Master,
            Update Conversion Rate
        '''
        obj = self.env['res.currency']
        RateObj = self.env['res.currency.rate']

        if not InvCurrencyCode: return obj

        Curr = obj.search([('name', '=', InvCurrencyCode)])
        InvCurrency = Curr and Curr[0] or obj

        Curr = obj.search([('name', '=', DefCurrencyCode)])
        CompanyCurrency = Curr and Curr[0] or obj

        # Update Conversion Rate:
        if DefCurrencyCode and InvCurrency != CompanyCurrency:
            InvCurrency = InvCurrency.with_env(self.env)
            CompanyCurrency = CompanyCurrency.with_env(self.env)

            if InvCurrency.rate != Rate:
                RateObj.create({'name': EffDate,
                             'rate': Rate,
                             'currency_id': InvCurrency.id,
                             'company_id': Company.id,
                             })
        return InvCurrency


    def _prepare_xeroInvoice_data(self, invoices):
        context = dict(self._context)
        NewVals = {}

        def _prepare_lines(invoice_line_ids):
            lines = []
            for l in invoice_line_ids:
                acc = 200
                if l.account_id.id_xero:
                    acc = l.account_id.code

                lv = {
                    'Description': l.name or '',
                    'Quantity': l.quantity,
                    'UnitAmount': l.price_unit,
                    'AccountCode': acc,
                    }

                if l.product_id:
                    if not l.product_id.id_xero:
                        ctx = context.copy()
                        ctx['productID'] = l.product_id.id
                        self.with_context(ctx).action_export_products()

                    prodCode = l.product_id.default_code or l.product_id.name
                    lv['ItemCode'] = prodCode

                lines.append(lv)
            return lines

        for i in invoices:
            if not i.partner_id.id_xero:
                ctx = context.copy()
                ctx['partnerID'] = i.partner_id.id
                self.with_context(ctx).action_export_contacts()

            ContactID = i.partner_id.id_xero

            lines = _prepare_lines(i.invoice_line_ids)

            Type = 'ACCREC'
            if i.type == 'out_invoice': Type = 'ACCREC'
            elif i.type == 'in_invoice': Type = 'ACCPAY'
            elif i.type == 'out_refund': Type = 'ACCRECCREDIT'
            elif i.type == 'in_refund': Type = 'ACCPAYCREDIT'

            if i.date_invoice:
                idate = fields.Datetime.from_string(i.date_invoice)
            else:
                idate = fields.Datetime.from_string(i.create_date)

            vals = {
                'Type': Type,
                'Contact': {'ContactID': ContactID},
                'Date': idate,
                'LineAmountTypes': u'Exclusive',
                'Reference': (i.lead_id and i.lead_id.enq_number or i.origin) or '',
                'LineItems': lines,
                'CurrencyCode': i.currency_id.name,
                'DefaultCurrencyCode': i.company_id.currency_id.name,
            }

            if i.date_due:
                vals['DueDate'] = fields.Datetime.from_string(i.date_due)

            NewVals[i] = vals
        return NewVals