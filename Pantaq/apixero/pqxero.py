# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class PantaqXero(models.Model):
    _name = 'pantaq.xero.history'
    _order = 'date_run desc'

    name = fields.Text('Description')
    date_run = fields.Datetime('Connection Run Datetime')
    type = fields.Selection([('import_contacts', 'Import Contacts'), ('export_contacts', 'Export Contacts'),
                             ('import_invoices', 'Import Invoices'), ('export_invoices', 'Export Invoices'),
                             ('import_products', 'Import Products'), ('export_products', 'Export Products'),
                             ('import_accounts', 'Import Accounts'),
                             ('import_taxes', 'Import Taxes'),
                             ('import_payments', 'Import Payments')
                             ])

