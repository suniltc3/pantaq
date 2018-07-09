
from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp


class ProductProduct(models.Model):
    _inherit = ["product.product"]

    id_xero = fields.Char('ID Reference of Xero', copy=False)
