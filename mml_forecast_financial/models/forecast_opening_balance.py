import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

_ITEMS = ['cash', 'receivables', 'inventory', 'payables', 'equity']

# --- Pure-Python helper (also tested directly) ---

def effective_value(auto, manual, override):
    """Return manual if override is True, else auto."""
    return manual if override else auto


class ForecastOpeningBalance(models.Model):
    _name = 'forecast.opening.balance'
    _description = 'Forecast Opening Balance Sheet Position'
    _rec_name = 'config_id'

    _sql_constraints = [
        ('config_unique', 'UNIQUE(config_id)',
         'Only one opening balance record is allowed per forecast config.'),
    ]

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )

    # --- Cash ---
    opening_cash = fields.Float(string='Cash (Auto)', digits=(16, 2))
    opening_cash_manual = fields.Float(string='Cash (Manual)', digits=(16, 2))
    override_cash = fields.Boolean(string='Override Cash', default=False)
    effective_cash = fields.Float(
        string='Cash (Effective)',
        compute='_compute_effective',
        digits=(16, 2),
    )

    # --- Receivables ---
    opening_receivables = fields.Float(string='Receivables (Auto)', digits=(16, 2))
    opening_receivables_manual = fields.Float(string='Receivables (Manual)', digits=(16, 2))
    override_receivables = fields.Boolean(string='Override Receivables', default=False)
    effective_receivables = fields.Float(
        string='Receivables (Effective)',
        compute='_compute_effective',
        digits=(16, 2),
    )

    # --- Inventory ---
    opening_inventory = fields.Float(string='Inventory (Auto)', digits=(16, 2))
    opening_inventory_manual = fields.Float(string='Inventory (Manual)', digits=(16, 2))
    override_inventory = fields.Boolean(string='Override Inventory', default=False)
    effective_inventory = fields.Float(
        string='Inventory (Effective)',
        compute='_compute_effective',
        digits=(16, 2),
    )

    # --- Payables ---
    opening_payables = fields.Float(string='Payables (Auto)', digits=(16, 2))
    opening_payables_manual = fields.Float(string='Payables (Manual)', digits=(16, 2))
    override_payables = fields.Boolean(string='Override Payables', default=False)
    effective_payables = fields.Float(
        string='Payables (Effective)',
        compute='_compute_effective',
        digits=(16, 2),
    )

    # --- Equity ---
    opening_equity = fields.Float(string='Equity (Auto)', digits=(16, 2))
    opening_equity_manual = fields.Float(string='Equity (Manual)', digits=(16, 2))
    override_equity = fields.Boolean(string='Override Equity', default=False)
    effective_equity = fields.Float(
        string='Equity (Effective)',
        compute='_compute_effective',
        digits=(16, 2),
    )

    @api.depends(
        'opening_cash', 'opening_cash_manual', 'override_cash',
        'opening_receivables', 'opening_receivables_manual', 'override_receivables',
        'opening_inventory', 'opening_inventory_manual', 'override_inventory',
        'opening_payables', 'opening_payables_manual', 'override_payables',
        'opening_equity', 'opening_equity_manual', 'override_equity',
    )
    def _compute_effective(self):
        for rec in self:
            for item in _ITEMS:
                auto = getattr(rec, f'opening_{item}')
                manual = getattr(rec, f'opening_{item}_manual')
                override = getattr(rec, f'override_{item}')
                setattr(rec, f'effective_{item}', effective_value(auto, manual, override))

    def _pull_from_accounting(self, date_start):
        """
        Query account.move.line trial balance at date_start and populate opening_<item> fields.
        Only overwrites fields where override_<item> is False.

        account_type groupings:
          cash        -> asset_cash, asset_bank
          receivables -> asset_receivable
          inventory   -> asset_current, asset_valuation
          payables    -> liability_payable
          equity      -> equity, equity_unaffected plus income/expense residuals
                         (cumulative P&L roll-up -- trial balance before period-close)
        """
        AccountMoveLine = self.env['account.move.line']
        company_id = self.config_id.company_id.id

        lines = AccountMoveLine.search([
            ('date', '<', date_start),
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

        vals = {}
        for item in _ITEMS:
            if not getattr(self, f'override_{item}'):
                vals[f'opening_{item}'] = totals[item]

        if vals:
            self.write(vals)

        _logger.info(
            'Pulled opening balance for config %s at %s: cash=%.2f receivables=%.2f '
            'inventory=%.2f payables=%.2f equity=%.2f',
            self.config_id.id, date_start,
            totals['cash'], totals['receivables'], totals['inventory'],
            totals['payables'], totals['equity'],
        )
