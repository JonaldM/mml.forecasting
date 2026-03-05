from odoo import models, fields


class ForecastRevenueLine(models.Model):
    _name = 'forecast.revenue.line'
    _description = 'Forecast Revenue Line'
    _order = 'period_start, partner_id, product_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period', help='E.g. 2026-04')

    # Dimensions
    product_id = fields.Many2one('product.product', string='Product')
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        related='product_id.product_tmpl_id',
        store=True,
    )
    partner_id = fields.Many2one('res.partner', string='Customer')
    brand = fields.Char(string='Brand')
    category = fields.Char(string='Category')

    # Values
    forecast_units = fields.Float(string='Forecast Units', digits=(12, 0))
    sell_price_unit = fields.Float(string='Sell Price / Unit (NZD)', digits=(12, 4))
    revenue = fields.Float(
        string='Revenue (NZD)',
        compute='_compute_revenue',
        store=True,
    )

    def _compute_revenue(self):
        for rec in self:
            rec.revenue = rec.forecast_units * rec.sell_price_unit
