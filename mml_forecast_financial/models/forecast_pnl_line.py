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
    currency_id = fields.Many2one(
        'res.currency',
        related='config_id.company_id.currency_id',
        store=True,
        string='Currency',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # Revenue
    revenue = fields.Monetary(string='Revenue (NZD)', currency_field='currency_id')

    # COGS breakdown
    cogs_fob = fields.Monetary(string='FOB Cost (NZD)', currency_field='currency_id')
    cogs_freight = fields.Monetary(string='Freight (NZD)', currency_field='currency_id')
    cogs_duty = fields.Monetary(string='Duty (NZD)', currency_field='currency_id')
    cogs_3pl = fields.Monetary(string='3PL (NZD)', currency_field='currency_id')
    total_cogs = fields.Monetary(
        string='Total COGS (NZD)',
        currency_field='currency_id',
        compute='_compute_margins',
        store=True,
    )

    # Margins
    gross_margin = fields.Monetary(
        string='Gross Margin (NZD)',
        currency_field='currency_id',
        compute='_compute_margins',
        store=True,
    )
    gross_margin_pct = fields.Float(
        string='GM %',
        compute='_compute_margins',
        store=True,
    )

    # OpEx
    opex_fixed = fields.Monetary(string='Fixed OpEx (NZD)', currency_field='currency_id')
    opex_variable = fields.Monetary(string='Variable OpEx (NZD)', currency_field='currency_id')
    total_opex = fields.Monetary(
        string='Total OpEx (NZD)',
        currency_field='currency_id',
        compute='_compute_margins',
        store=True,
    )

    # Bottom line
    ebitda = fields.Monetary(
        string='EBITDA (NZD)',
        currency_field='currency_id',
        compute='_compute_margins',
        store=True,
    )
    ebitda_pct = fields.Float(
        string='EBITDA %',
        compute='_compute_margins',
        store=True,
    )

    # --- Actuals (populated by action_compute_variance) ---
    actual_revenue = fields.Monetary(
        string='Actual Revenue (NZD)',
        currency_field='currency_id',
    )
    actual_cogs = fields.Monetary(
        string='Actual COGS (NZD)',
        currency_field='currency_id',
    )
    actual_opex = fields.Monetary(
        string='Actual OpEx (NZD)',
        currency_field='currency_id',
    )

    actual_gross_margin = fields.Monetary(
        string='Actual Gross Margin (NZD)',
        currency_field='currency_id',
        compute='_compute_actuals',
    )
    actual_ebitda = fields.Monetary(
        string='Actual EBITDA (NZD)',
        currency_field='currency_id',
        compute='_compute_actuals',
    )

    # --- Variance ---
    variance_revenue = fields.Monetary(
        string='Variance Revenue (NZD)',
        currency_field='currency_id',
        compute='_compute_actuals',
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
