from odoo import models, fields, api


class ForecastPnlLine(models.Model):
    _name = 'forecast.pnl.line'
    _description = 'Forecast P&L Summary Line'
    _order = 'period_start'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # Revenue
    revenue = fields.Float(string='Revenue (NZD)')

    # COGS breakdown
    cogs_fob = fields.Float(string='FOB Cost (NZD)')
    cogs_freight = fields.Float(string='Freight (NZD)')
    cogs_duty = fields.Float(string='Duty (NZD)')
    cogs_3pl = fields.Float(string='3PL (NZD)')
    total_cogs = fields.Float(
        string='Total COGS (NZD)',
        compute='_compute_margins',
        store=True,
    )

    # Margins
    gross_margin = fields.Float(
        string='Gross Margin (NZD)',
        compute='_compute_margins',
        store=True,
    )
    gross_margin_pct = fields.Float(
        string='GM %',
        compute='_compute_margins',
        store=True,
    )

    # OpEx
    opex_fixed = fields.Float(string='Fixed OpEx (NZD)')
    opex_variable = fields.Float(string='Variable OpEx (NZD)')
    total_opex = fields.Float(
        string='Total OpEx (NZD)',
        compute='_compute_margins',
        store=True,
    )

    # Bottom line
    ebitda = fields.Float(
        string='EBITDA (NZD)',
        compute='_compute_margins',
        store=True,
    )
    ebitda_pct = fields.Float(
        string='EBITDA %',
        compute='_compute_margins',
        store=True,
    )

    # --- Actuals (populated by action_compute_variance) ---
    actual_revenue = fields.Float(string='Actual Revenue (NZD)', digits=(16, 2))
    actual_cogs = fields.Float(string='Actual COGS (NZD)', digits=(16, 2))
    actual_opex = fields.Float(string='Actual OpEx (NZD)', digits=(16, 2))

    actual_gross_margin = fields.Float(
        string='Actual Gross Margin (NZD)',
        compute='_compute_actuals',
        digits=(16, 2),
    )
    actual_ebitda = fields.Float(
        string='Actual EBITDA (NZD)',
        compute='_compute_actuals',
        digits=(16, 2),
    )

    # --- Variance ---
    variance_revenue = fields.Float(
        string='Variance Revenue (NZD)',
        compute='_compute_actuals',
        digits=(16, 2),
    )
    variance_revenue_pct = fields.Float(
        string='Variance Revenue %',
        compute='_compute_actuals',
        digits=(5, 2),
    )
    variance_ebitda_pct = fields.Float(
        string='Variance EBITDA %',
        compute='_compute_actuals',
        digits=(5, 2),
    )

    @api.depends(
        'revenue', 'cogs_fob', 'cogs_freight', 'cogs_duty', 'cogs_3pl',
        'opex_fixed', 'opex_variable',
    )
    def _compute_margins(self):
        for rec in self:
            rec.total_cogs = (
                rec.cogs_fob + rec.cogs_freight + rec.cogs_duty + rec.cogs_3pl
            )
            rec.gross_margin = rec.revenue - rec.total_cogs
            rec.gross_margin_pct = (
                (rec.gross_margin / rec.revenue * 100) if rec.revenue else 0.0
            )
            rec.total_opex = rec.opex_fixed + rec.opex_variable
            rec.ebitda = rec.gross_margin - rec.total_opex
            rec.ebitda_pct = (
                (rec.ebitda / rec.revenue * 100) if rec.revenue else 0.0
            )

    @api.depends('actual_revenue', 'actual_cogs', 'actual_opex', 'revenue', 'ebitda')
    def _compute_actuals(self):
        for rec in self:
            rec.actual_gross_margin = rec.actual_revenue - rec.actual_cogs
            rec.actual_ebitda = rec.actual_gross_margin - rec.actual_opex
            rec.variance_revenue = rec.actual_revenue - rec.revenue
            rec.variance_revenue_pct = (
                (rec.variance_revenue / rec.revenue * 100) if rec.revenue else 0.0
            )
            rec.variance_ebitda_pct = (
                ((rec.actual_ebitda - rec.ebitda) / rec.ebitda * 100)
                if rec.ebitda else 0.0
            )
