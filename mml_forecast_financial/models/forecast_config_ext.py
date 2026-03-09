from odoo import models, fields, api


class ForecastConfigFinancialExt(models.Model):
    """
    Extends forecast.config with financial One2many relationships.

    These fields live here (not in mml_forecast_core) because the comodels
    (forecast.revenue.line, etc.) are defined in this module. Odoo 19 validates
    comodels during _setup_models__ before dependent modules load, so forward
    references from core to financial cause install failures.
    """
    _inherit = 'forecast.config'

    revenue_line_ids = fields.One2many(
        'forecast.revenue.line', 'config_id', string='Revenue Lines',
    )
    cogs_line_ids = fields.One2many(
        'forecast.cogs.line', 'config_id', string='COGS Lines',
    )
    pnl_line_ids = fields.One2many(
        'forecast.pnl.line', 'config_id', string='P&L Lines',
    )
    cashflow_line_ids = fields.One2many(
        'forecast.cashflow.line', 'config_id', string='Cash Flow Lines',
    )
    opex_line_ids = fields.One2many(
        'forecast.opex.line', 'config_id', string='Operating Expenses',
    )

    @api.depends('pnl_line_ids.revenue', 'pnl_line_ids.total_cogs', 'pnl_line_ids.gross_margin')
    def _compute_totals(self):
        for rec in self:
            lines = rec.pnl_line_ids
            rec.total_revenue = sum(lines.mapped('revenue'))
            rec.total_cogs = sum(lines.mapped('total_cogs'))
            rec.total_gross_margin = sum(lines.mapped('gross_margin'))
            rec.gross_margin_pct = (
                (rec.total_gross_margin / rec.total_revenue * 100)
                if rec.total_revenue else 0.0
            )
