from odoo import models, fields


class ProductTemplateForecasting(models.Model):
    """
    Extension of product.template for forecasting cost drivers.

    Adds x_cbm_per_unit and x_3pl_pick_rate — custom fields (x_ prefix = Odoo Studio
    convention) used by the financial forecasting COGS waterfall. The wizard reads these
    via getattr() for zero-safe access when no value is set on a product.

    Lives in mml_forecast_core (not financial) so mml_forecast_demand can also
    reference these fields without a dependency on mml_forecast_financial.
    """
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
