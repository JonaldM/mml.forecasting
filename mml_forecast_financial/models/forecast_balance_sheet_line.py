from odoo import models, fields, api


class ForecastBalanceSheetLine(models.Model):
    _name = 'forecast.balance.sheet.line'
    _description = 'Forecast Balance Sheet Line'
    _order = 'period_start'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # --- Assets (stored — written by wizard) ---
    cash = fields.Float(string='Cash (NZD)', digits=(16, 2))
    trade_receivables = fields.Float(string='Trade Receivables (NZD)', digits=(16, 2))
    inventory_value = fields.Float(string='Inventory (NZD)', digits=(16, 2))

    # --- Liabilities (stored) ---
    trade_payables = fields.Float(string='Trade Payables (NZD)', digits=(16, 2))

    # --- Equity (stored) ---
    retained_earnings = fields.Float(string='Retained Earnings (NZD)', digits=(16, 2))

    # --- Computed summaries (not stored) ---
    total_current_assets = fields.Float(
        string='Total Current Assets (NZD)',
        compute='_compute_bs_totals',
        digits=(16, 2),
    )
    total_current_liabilities = fields.Float(
        string='Total Current Liabilities (NZD)',
        compute='_compute_bs_totals',
        digits=(16, 2),
    )
    total_equity = fields.Float(
        string='Total Equity (NZD)',
        compute='_compute_bs_totals',
        digits=(16, 2),
    )
    total_assets = fields.Float(
        string='Total Assets (NZD)',
        compute='_compute_bs_totals',
        digits=(16, 2),
    )
    bs_difference = fields.Float(
        string='BS Check (NZD)',
        compute='_compute_bs_totals',
        digits=(16, 2),
        help='Total Assets minus (Total Liabilities + Total Equity). '
             'Non-zero due to simplified model (no fixed assets, GST credits, etc.). '
             'Displayed in red if > 1%% of total assets.',
    )

    @api.depends(
        'cash', 'trade_receivables', 'inventory_value',
        'trade_payables', 'retained_earnings',
    )
    def _compute_bs_totals(self):
        for rec in self:
            rec.total_current_assets = (
                rec.cash + rec.trade_receivables + rec.inventory_value
            )
            rec.total_current_liabilities = rec.trade_payables
            rec.total_equity = rec.retained_earnings
            rec.total_assets = rec.total_current_assets
            rec.bs_difference = rec.total_assets - (
                rec.total_current_liabilities + rec.total_equity
            )
