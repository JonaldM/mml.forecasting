from odoo import models, fields


class ProductTemplateForecasting(models.Model):
    _inherit = 'product.template'

    x_cbm_per_unit = fields.Float(
        string='CBM per Unit',
        digits=(12, 6),
        help='Cubic metres per unit. Used to calculate freight cost in forecasts.',
    )
    x_3pl_pick_rate = fields.Float(
        string='3PL Pick Rate (NZD/unit)',
        digits=(12, 4),
        help='Mainfreight pick/pack/despatch cost per unit. Used in COGS waterfall.',
    )
