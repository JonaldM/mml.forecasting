from odoo import models, fields, api


# --- Pure-Python helper ---

def variance_pct(actual, forecast):
    """Compute variance percentage. Returns 0.0 if forecast is zero."""
    if not forecast:
        return 0.0
    return (actual - forecast) / forecast * 100.0


class ForecastVarianceLine(models.Model):
    _name = 'forecast.variance.line'
    _description = 'Forecast vs Actual Variance Line'
    _order = 'period_start, product_id, partner_id'

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
    period_label = fields.Char(string='Period')

    # Dimensions
    product_id = fields.Many2one('product.product', string='Product')
    partner_id = fields.Many2one('res.partner', string='Customer')
    brand = fields.Char(string='Brand')
    category = fields.Char(string='Category')

    # Forecast values (from forecast.revenue.line)
    forecast_units = fields.Float(string='Forecast Units', digits=(12, 2))
    forecast_revenue = fields.Monetary(
        string='Forecast Revenue (NZD)',
        currency_field='currency_id',
    )

    # Actual values (from sale.order.line)
    actual_units = fields.Float(string='Actual Units', digits=(12, 2))
    actual_revenue = fields.Monetary(
        string='Actual Revenue (NZD)',
        currency_field='currency_id',
    )

    # Computed variances
    variance_units = fields.Float(
        string='Variance Units',
        compute='_compute_variance',
        digits=(12, 2),
    )
    variance_revenue = fields.Monetary(
        string='Variance Revenue (NZD)',
        currency_field='currency_id',
        compute='_compute_variance',
    )
    variance_revenue_pct = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        digits=(5, 2),
        help='Positive = actual beat forecast.',
    )

    @api.depends('actual_units', 'forecast_units', 'actual_revenue', 'forecast_revenue')
    def _compute_variance(self):
        for rec in self:
            rec.variance_units = rec.actual_units - rec.forecast_units
            rec.variance_revenue = rec.actual_revenue - rec.forecast_revenue
            rec.variance_revenue_pct = variance_pct(rec.actual_revenue, rec.forecast_revenue)
