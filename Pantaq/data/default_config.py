# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

class PantaqConfiguration(models.TransientModel):
    _name = 'pantaq.config.settings'
    _inherit = 'res.config.settings'

    purchase_markup = fields.Char('Procurement Markup/Margin',
        help ="Set the threshold Markup/Margin Value for Procurement")

    sale_markup = fields.Char('Sales Markup/Margin',
        help ="Set the threshold Markup/Margin Value for Sales")

    @api.model
    def get_default_values(self, fields):
        IrConfigParam = self.env['ir.config_parameter']
        # we use safe_eval on the result, since the value of the parameter is a nonempty string
        return {
            'purchase_markup': safe_eval(IrConfigParam.get_param('purchase_markup', '0')),
            'sale_markup': safe_eval(IrConfigParam.get_param('sale_markup', '0')),
        }

    @api.multi
    def set_default_values(self):
        for record in self:
            self.env['ir.config_parameter'].set_param("purchase_markup", record.purchase_markup or '0')
            self.env['ir.config_parameter'].set_param("sale_markup", record.sale_markup or '0')



