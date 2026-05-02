from odoo import models, fields, api


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
    currency_id = fields.Many2one(
        'res.currency',
        related='config_id.company_id.currency_id',
        store=True,
        string='Currency',
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
    sell_price_unit = fields.Monetary(
        string='Sell Price / Unit (NZD)',
        currency_field='currency_id',
    )
    revenue = fields.Monetary(
        string='Revenue (NZD)',
        currency_field='currency_id',
        compute='_compute_revenue',
        store=True,
    )
    receipt_month = fields.Date(
        string='Receipt Month',
        help='First day of the month in which this revenue is expected to be received by the customer. '
             'Computed from forecast.customer.term at generation time.',
    )

    @api.depends('forecast_units', 'sell_price_unit')
    def _compute_revenue(self):
        for rec in self:
            rec.revenue = rec.forecast_units * rec.sell_price_unit
