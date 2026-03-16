import logging

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

_ITEMS = ['cash', 'receivables', 'inventory', 'payables', 'equity']


class ForecastConfigFinancialExt(models.Model):
    """
    Extends forecast.config with financial relationships, opening balance fields,
    KPI aggregates, and setup completion flags.

    These fields live here (not in mml_forecast_core) because:
    - The One2many comodels (forecast.revenue.line, etc.) are defined in this module.
    - The accounting integration (trial balance query, company_id) belongs here.
    - Odoo 19 validates comodels during _setup_models__ before dependent modules load,
      so forward references from core to financial cause install failures.
    """
    _inherit = 'forecast.config'

    # -------------------------------------------------------------------------
    # Company (required for accounting trial balance query)
    # -------------------------------------------------------------------------
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # -------------------------------------------------------------------------
    # One2many relationships
    # -------------------------------------------------------------------------
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
    balance_sheet_line_ids = fields.One2many(
        'forecast.balance.sheet.line', 'config_id', string='Balance Sheet Lines',
    )
    variance_line_ids = fields.One2many(
        'forecast.variance.line', 'config_id', string='Variance Lines',
    )

    # -------------------------------------------------------------------------
    # Opening balance: Cash
    # -------------------------------------------------------------------------
    opening_cash = fields.Float(string='Cash (Auto)', digits=(16, 2))
    override_cash = fields.Boolean(string='Override Cash', default=False)
    opening_cash_manual = fields.Float(string='Cash (Manual)', digits=(16, 2))
    effective_cash = fields.Float(
        string='Cash (Effective)',
        compute='_compute_effective_cash',
        digits=(16, 2),
    )

    # -------------------------------------------------------------------------
    # Opening balance: Receivables
    # -------------------------------------------------------------------------
    opening_receivables = fields.Float(string='Receivables (Auto)', digits=(16, 2))
    override_receivables = fields.Boolean(string='Override Receivables', default=False)
    opening_receivables_manual = fields.Float(string='Receivables (Manual)', digits=(16, 2))
    effective_receivables = fields.Float(
        string='Receivables (Effective)',
        compute='_compute_effective_receivables',
        digits=(16, 2),
    )

    # -------------------------------------------------------------------------
    # Opening balance: Inventory
    # -------------------------------------------------------------------------
    opening_inventory = fields.Float(string='Inventory (Auto)', digits=(16, 2))
    override_inventory = fields.Boolean(string='Override Inventory', default=False)
    opening_inventory_manual = fields.Float(string='Inventory (Manual)', digits=(16, 2))
    effective_inventory = fields.Float(
        string='Inventory (Effective)',
        compute='_compute_effective_inventory',
        digits=(16, 2),
    )

    # -------------------------------------------------------------------------
    # Opening balance: Payables
    # -------------------------------------------------------------------------
    opening_payables = fields.Float(string='Payables (Auto)', digits=(16, 2))
    override_payables = fields.Boolean(string='Override Payables', default=False)
    opening_payables_manual = fields.Float(string='Payables (Manual)', digits=(16, 2))
    effective_payables = fields.Float(
        string='Payables (Effective)',
        compute='_compute_effective_payables',
        digits=(16, 2),
    )

    # -------------------------------------------------------------------------
    # Opening balance: Equity
    # -------------------------------------------------------------------------
    opening_equity = fields.Float(string='Equity (Auto)', digits=(16, 2))
    override_equity = fields.Boolean(string='Override Equity', default=False)
    opening_equity_manual = fields.Float(string='Equity (Manual)', digits=(16, 2))
    effective_equity = fields.Float(
        string='Equity (Effective)',
        compute='_compute_effective_equity',
        digits=(16, 2),
    )

    # -------------------------------------------------------------------------
    # Opening balance: pull flag
    # -------------------------------------------------------------------------
    opening_balance_pulled = fields.Boolean(
        string='Opening Balance Pulled',
        default=False,
    )

    # -------------------------------------------------------------------------
    # KPI aggregates (non-stored computed from child lines)
    # Float -- NOT Monetary -- because forecast.config has no currency_id field.
    # The monetary widget requires a currency_field attribute; plain Float avoids
    # that constraint. The view provides a "$" prefix label for visual context.
    # -------------------------------------------------------------------------
    kpi_total_revenue = fields.Float(
        string='12-Mo Revenue', digits=(16, 2), compute='_compute_kpis',
    )
    kpi_ebitda = fields.Float(
        string='EBITDA', digits=(16, 2), compute='_compute_kpis',
    )
    kpi_total_cogs = fields.Float(
        string='Total COGS', digits=(16, 2), compute='_compute_kpis',
    )
    kpi_ending_cash = fields.Float(
        string='Ending Cash', digits=(16, 2), compute='_compute_kpis',
    )
    kpi_cash_low_value = fields.Float(
        string='Cash Low Point', digits=(16, 2), compute='_compute_kpis',
    )
    kpi_cash_low_month = fields.Char(
        string='Cash Low Month', compute='_compute_kpis',
    )

    # -------------------------------------------------------------------------
    # Setup completion booleans (non-stored computed, drive progress tracker)
    # -------------------------------------------------------------------------
    setup_period_done = fields.Boolean(compute='_compute_setup_progress')
    setup_fx_done = fields.Boolean(compute='_compute_setup_progress')
    setup_terms_done = fields.Boolean(compute='_compute_setup_progress')
    setup_ob_done = fields.Boolean(compute='_compute_setup_progress')
    setup_opex_done = fields.Boolean(compute='_compute_setup_progress')

    # =========================================================================
    # Compute: _compute_totals (override from core no-op)
    # =========================================================================
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

    # =========================================================================
    # Compute: effective_* fields (one method per group for efficient invalidation)
    # =========================================================================
    @api.depends('opening_cash', 'override_cash', 'opening_cash_manual')
    def _compute_effective_cash(self):
        for rec in self:
            rec.effective_cash = rec.opening_cash_manual if rec.override_cash else rec.opening_cash

    @api.depends('opening_receivables', 'override_receivables', 'opening_receivables_manual')
    def _compute_effective_receivables(self):
        for rec in self:
            rec.effective_receivables = (
                rec.opening_receivables_manual if rec.override_receivables
                else rec.opening_receivables
            )

    @api.depends('opening_inventory', 'override_inventory', 'opening_inventory_manual')
    def _compute_effective_inventory(self):
        for rec in self:
            rec.effective_inventory = (
                rec.opening_inventory_manual if rec.override_inventory
                else rec.opening_inventory
            )

    @api.depends('opening_payables', 'override_payables', 'opening_payables_manual')
    def _compute_effective_payables(self):
        for rec in self:
            rec.effective_payables = (
                rec.opening_payables_manual if rec.override_payables
                else rec.opening_payables
            )

    @api.depends('opening_equity', 'override_equity', 'opening_equity_manual')
    def _compute_effective_equity(self):
        for rec in self:
            rec.effective_equity = (
                rec.opening_equity_manual if rec.override_equity
                else rec.opening_equity
            )

    # =========================================================================
    # Compute: KPI aggregates
    # =========================================================================
    @api.depends(
        'pnl_line_ids.revenue', 'pnl_line_ids.ebitda', 'pnl_line_ids.total_cogs',
        'cashflow_line_ids.cumulative_cashflow', 'cashflow_line_ids.period_label',
    )
    def _compute_kpis(self):
        for rec in self:
            rec.kpi_total_revenue = sum(rec.pnl_line_ids.mapped('revenue'))
            rec.kpi_ebitda = sum(rec.pnl_line_ids.mapped('ebitda'))
            rec.kpi_total_cogs = sum(rec.pnl_line_ids.mapped('total_cogs'))
            cf = rec.cashflow_line_ids.sorted('id')
            if cf:
                rec.kpi_ending_cash = cf[-1].cumulative_cashflow
                min_line = min(cf, key=lambda l: l.cumulative_cashflow)
                rec.kpi_cash_low_value = min_line.cumulative_cashflow
                rec.kpi_cash_low_month = min_line.period_label
            else:
                rec.kpi_ending_cash = 0.0
                rec.kpi_cash_low_value = 0.0
                rec.kpi_cash_low_month = ''

    # =========================================================================
    # Compute: setup completion booleans
    # =========================================================================
    @api.depends(
        'date_start', 'fx_rate_ids', 'customer_term_ids',
        'supplier_term_ids', 'opening_balance_pulled', 'opex_line_ids',
    )
    def _compute_setup_progress(self):
        for rec in self:
            rec.setup_period_done = bool(rec.date_start)
            rec.setup_fx_done = bool(rec.fx_rate_ids)
            rec.setup_terms_done = bool(rec.customer_term_ids or rec.supplier_term_ids)
            rec.setup_ob_done = bool(rec.opening_balance_pulled)
            rec.setup_opex_done = bool(rec.opex_line_ids)

    # =========================================================================
    # Actions
    # =========================================================================
    def action_pull_opening_balance(self):
        self.ensure_one()
        self._pull_opening_balance_from_accounting()
        self.opening_balance_pulled = True
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

        balance_sheet_line_ids and variance_line_ids are defined here (financial
        module) -- they are not visible to the core module at code-read time.
        Opening balance fields are stored directly on forecast.config and persist
        across regenerations by design (accounting pull is expensive; manual
        overrides should survive a re-generate).
        """
        super().action_reset_draft()
        self.balance_sheet_line_ids.unlink()
        self.variance_line_ids.unlink()

    # =========================================================================
    # Private: opening balance accounting query
    # =========================================================================
    def _pull_opening_balance_from_accounting(self):
        """
        Query account.move.line trial balance at self.date_start and write results
        to opening_<item> fields. Always writes all auto fields regardless of
        override state -- the override flag and effective_* compute handle which
        value is used downstream.

        account_type groupings:
          cash        -> asset_cash, asset_bank
          receivables -> asset_receivable
          inventory   -> asset_current, asset_valuation
          payables    -> liability_payable
          equity      -> equity, equity_unaffected plus income/expense residuals
                         (cumulative P&L roll-up -- trial balance before period-close)
        """
        AccountMoveLine = self.env['account.move.line']
        company_id = self.company_id.id

        lines = AccountMoveLine.search([
            ('date', '<', self.date_start),
            ('company_id', '=', company_id),
            ('move_id.state', '=', 'posted'),
        ])

        type_map = {
            'cash': ('asset_cash', 'asset_bank'),
            'receivables': ('asset_receivable',),
            'inventory': ('asset_current', 'asset_valuation'),
            'payables': ('liability_payable',),
            'equity': ('equity', 'equity_unaffected', 'income', 'income_other',
                       'expense', 'expense_direct_cost'),
        }

        totals = {item: 0.0 for item in _ITEMS}
        for aml in lines:
            atype = aml.account_id.account_type
            for item, types in type_map.items():
                if atype in types:
                    totals[item] += aml.debit - aml.credit

        # Always write the auto opening_* fields -- they represent the raw accounting value.
        # The override flag and effective_* compute handle which value is used downstream.
        self.write({f'opening_{item}': totals[item] for item in _ITEMS})

        _logger.info(
            'Pulled opening balance for config %s at %s: '
            'cash=%.2f receivables=%.2f inventory=%.2f payables=%.2f equity=%.2f',
            self.id, self.date_start,
            totals['cash'], totals['receivables'], totals['inventory'],
            totals['payables'], totals['equity'],
        )
