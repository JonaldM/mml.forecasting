from odoo import models, fields, api


class ForecastFxRate(models.Model):
    _name = 'forecast.fx.rate'
    _description = 'Forecast FX Rate'
    _order = 'currency_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
    )
    rate_to_nzd = fields.Float(
        string='Rate to NZD',
        digits=(12, 4),
        required=True,
        help=(
            'How many NZD per 1 unit of foreign currency. '
            'E.g. USD rate of 0.60 means 1 NZD = 0.60 USD, '
            'so 1 USD = 1/0.60 = 1.6667 NZD.'
        ),
    )
    nzd_per_unit = fields.Float(
        string='NZD per 1 FCY',
        compute='_compute_nzd_per_unit',
        digits=(12, 4),
        store=True,
        help='Computed: how many NZD to buy 1 unit of foreign currency.',
    )
    notes = fields.Char(string='Notes')

    @api.depends('rate_to_nzd')
    def _compute_nzd_per_unit(self):
        for rec in self:
            rec.nzd_per_unit = (1.0 / rec.rate_to_nzd) if rec.rate_to_nzd else 0.0

    def get_rate(self, currency_code):
        """Return NZD-per-1-FCY for a given currency code within this config."""
        rate = self.filtered(
            lambda r: r.currency_id.name == currency_code
        )
        if rate:
            return rate[0].nzd_per_unit
        # Fallback: NZD to NZD = 1.0
        return 1.0
