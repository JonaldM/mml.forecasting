from odoo import models, fields, api


class ForecastCogsLine(models.Model):
    _name = 'forecast.cogs.line'
    _description = 'Forecast COGS Waterfall Line'
    _order = 'period_start, partner_id, product_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # Dimensions (mirror revenue line for easy join)
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

    forecast_units = fields.Float(string='Forecast Units', digits=(12, 0))

    # --- COGS Waterfall Components ---
    # FOB
    fob_unit_fcy = fields.Float(string='FOB / Unit (FCY)', digits=(12, 4))
    fob_currency = fields.Char(string='FOB Currency')
    fx_rate_applied = fields.Float(string='FX Rate (NZD per FCY)', digits=(12, 4))
    fob_unit_nzd = fields.Float(string='FOB / Unit (NZD)', digits=(12, 4))
    fob_total_nzd = fields.Float(
        string='FOB Total (NZD)',
        compute='_compute_totals',
        store=True,
    )

    # Freight
    cbm_per_unit = fields.Float(string='CBM / Unit', digits=(12, 6))
    freight_rate_cbm = fields.Float(string='Freight Rate ($/CBM)', digits=(12, 2))
    freight_unit_nzd = fields.Float(string='Freight / Unit (NZD)', digits=(12, 4))
    freight_total_nzd = fields.Float(
        string='Freight Total (NZD)',
        compute='_compute_totals',
        store=True,
    )

    # Duty
    tariff_rate_pct = fields.Float(string='Tariff Rate %', digits=(5, 2))
    duty_unit_nzd = fields.Float(string='Duty / Unit (NZD)', digits=(12, 4))
    duty_total_nzd = fields.Float(
        string='Duty Total (NZD)',
        compute='_compute_totals',
        store=True,
    )

    # 3PL
    tpl_pick_rate = fields.Float(string='3PL Pick Rate / Unit (NZD)', digits=(12, 4))
    tpl_total_nzd = fields.Float(
        string='3PL Total (NZD)',
        compute='_compute_totals',
        store=True,
    )

    # Totals
    landed_unit_nzd = fields.Float(
        string='Landed Cost / Unit (NZD)',
        compute='_compute_totals',
        store=True,
    )
    total_cogs_nzd = fields.Float(
        string='Total COGS (NZD)',
        compute='_compute_totals',
        store=True,
    )

    @api.depends(
        'forecast_units', 'fob_unit_nzd', 'freight_unit_nzd',
        'duty_unit_nzd', 'tpl_pick_rate', 'cbm_per_unit',
        'freight_rate_cbm', 'tariff_rate_pct', 'fob_unit_fcy',
        'fx_rate_applied',
    )
    def _compute_totals(self):
        for rec in self:
            u = rec.forecast_units

            # FOB in NZD
            rec.fob_unit_nzd = rec.fob_unit_fcy * rec.fx_rate_applied
            rec.fob_total_nzd = rec.fob_unit_nzd * u

            # Freight
            rec.freight_unit_nzd = rec.cbm_per_unit * rec.freight_rate_cbm
            rec.freight_total_nzd = rec.freight_unit_nzd * u

            # Duty (% of FOB NZD value)
            rec.duty_unit_nzd = rec.fob_unit_nzd * (rec.tariff_rate_pct / 100.0)
            rec.duty_total_nzd = rec.duty_unit_nzd * u

            # 3PL
            rec.tpl_total_nzd = rec.tpl_pick_rate * u

            # Landed
            rec.landed_unit_nzd = (
                rec.fob_unit_nzd
                + rec.freight_unit_nzd
                + rec.duty_unit_nzd
                + rec.tpl_pick_rate
            )
            rec.total_cogs_nzd = rec.landed_unit_nzd * u
