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
    currency_id = fields.Many2one(
        'res.currency',
        related='config_id.company_id.currency_id',
        store=True,
        string='Currency',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # --- Assets (stored — written by wizard) ---
    cash = fields.Monetary(string='Cash (NZD)', currency_field='currency_id')
    trade_receivables = fields.Monetary(
        string='Trade Receivables (NZD)',
        currency_field='currency_id',
    )
    inventory_value = fields.Monetary(
        string='Inventory (NZD)',
        currency_field='currency_id',
    )

    # --- Liabilities (stored) ---
    trade_payables = fields.Monetary(
        string='Trade Payables (NZD)',
        currency_field='currency_id',
    )

    # --- Equity (stored) ---
    retained_earnings = fields.Monetary(
        string='Retained Earnings (NZD)',
        currency_field='currency_id',
    )

    # --- Computed summaries (not stored) ---
    total_current_assets = fields.Monetary(
        string='Total Current Assets (NZD)',
        currency_field='currency_id',
        compute='_compute_bs_totals',
    )
    total_current_liabilities = fields.Monetary(
        string='Total Current Liabilities (NZD)',
        currency_field='currency_id',
        compute='_compute_bs_totals',
    )
    total_equity = fields.Monetary(
        string='Total Equity (NZD)',
        currency_field='currency_id',
        compute='_compute_bs_totals',
    )
    total_assets = fields.Monetary(
        string='Total Assets (NZD)',
        currency_field='currency_id',
        compute='_compute_bs_totals',
    )
    bs_difference = fields.Monetary(
        string='BS Check (NZD)',
        currency_field='currency_id',
        compute='_compute_bs_totals',
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
