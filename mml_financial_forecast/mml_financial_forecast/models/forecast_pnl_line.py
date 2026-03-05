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
