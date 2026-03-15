from dateutil.relativedelta import relativedelta

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
    opening_balance_ids = fields.One2many(
        'forecast.opening.balance', 'config_id', string='Opening Balance',
    )
    balance_sheet_line_ids = fields.One2many(
        'forecast.balance.sheet.line', 'config_id', string='Balance Sheet Lines',
    )
    variance_line_ids = fields.One2many(
        'forecast.variance.line', 'config_id', string='Variance Lines',
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

    def action_pull_opening_balance(self):
        """
        Create or update the opening balance record from the Odoo accounting trial balance.
        Pulls account.move.line data as at config.date_start.
        """
        self.ensure_one()
        ob = self.opening_balance_ids[:1]
        if not ob:
            ob = self.env['forecast.opening.balance'].create({'config_id': self.id})
        ob._pull_from_accounting(self.date_start)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_compute_variance(self):
        """
        Recompute variance lines and P&L actuals for all past periods.
        Can be called independently of a full forecast regeneration.
        """
        self.ensure_one()
        months = []
        current = self.date_start.replace(day=1)
        for _ in range(self.horizon_months):
            months.append((current, current.strftime('%Y-%m')))
            current += relativedelta(months=1)
        self.env['forecast.generate.wizard']._compute_variance_lines(self, months)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_reset_draft(self):
        """
        Override core action_reset_draft to also unlink BS and variance lines.

        This override lives in forecast_config_ext.py (financial module) because
        balance_sheet_line_ids and variance_line_ids are defined here — they are
        not visible to the core module at code-read time. opening_balance_ids is
        intentionally NOT unlinked — the accounting pull and manual overrides
        persist across regenerations.
        """
        super().action_reset_draft()
        self.balance_sheet_line_ids.unlink()
        self.variance_line_ids.unlink()
