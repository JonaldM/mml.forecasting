# Castaway Parity Sprint — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `mml_forecast_financial` to Castaway parity by adding a full Balance Sheet, usable Odoo views, variance reporting, per-supplier cashflow timing, and product field population.

**Architecture:** All changes stay within `mml_forecast_core` and `mml_forecast_financial` — no new modules. Three new models (`forecast.opening.balance`, `forecast.balance.sheet.line`, `forecast.variance.line`), minor additions to four existing models, and a wizard refactor to produce the full 3-way integrated forecast (P&L + Balance Sheet + Cashflow).

**Tech Stack:** Odoo 19, Python 3, pure-Python pytest for structural tests, `odoo-bin --test-enable` for integration tests, git push → HIAV deploy for smoke testing.

---

## File Map

### `mml_forecast_core/` — 4 changes

| File | Action |
|------|--------|
| `models/__init__.py` | Modify — add `product_template_ext` import |
| `models/product_template_ext.py` | **Create** |
| `views/product_template_ext_views.xml` | **Create** |
| `__manifest__.py` | Modify — add view XML to `data[]` |

### `mml_forecast_financial/` — 19 changes

| File | Action |
|------|--------|
| `models/__init__.py` | Modify — add 3 new model imports |
| `models/forecast_cashflow_line.py` | Modify — split `payments_fob`, update `@api.depends` |
| `models/forecast_revenue_line.py` | Modify — add `receipt_month` field |
| `models/forecast_cogs_line.py` | Modify — add `supplier_id` field |
| `models/forecast_pnl_line.py` | Modify — add 5 actual/variance fields |
| `models/forecast_config_ext.py` | Modify — add 3 One2many fields + 2 action methods + override `action_reset_draft` |
| `models/forecast_opening_balance.py` | **Create** |
| `models/forecast_balance_sheet_line.py` | **Create** |
| `models/forecast_variance_line.py` | **Create** |
| `wizards/forecast_generate_wizard.py` | Modify — per-supplier timing, receipt_month, supplier_id, new pipeline steps |
| `views/forecast_financial_views.xml` | Modify — update config form (new tabs, buttons, split FOB) + add P&L pivot action |
| `views/forecast_balance_sheet_views.xml` | **Create** |
| `views/forecast_variance_views.xml` | **Create** |
| `security/ir.model.access.csv` | Modify — 6 new ACL rows (user + manager for 3 models) |
| `__manifest__.py` | Modify — add 2 new view XMLs to `data[]` |
| `tests/__init__.py` | **Create** |
| `tests/test_model_fields.py` | **Create** — pure-Python structural tests |
| `tests/test_bs_helpers.py` | **Create** — pure-Python BS math tests |
| `tests/test_per_supplier_timing.py` | **Create** — pure-Python per-supplier timing tests |

---

## Chunk 1: Infrastructure — Model Field Additions

### Task 1: Product field extensions in `mml_forecast_core`

**Files:**
- Create: `mml_forecast_core/models/product_template_ext.py`
- Create: `mml_forecast_core/views/product_template_ext_views.xml`
- Modify: `mml_forecast_core/models/__init__.py`
- Modify: `mml_forecast_core/__manifest__.py`

- [ ] **Step 1: Write failing structural test**

Create `mml_forecast_financial/tests/__init__.py` (empty):
```python
```

Create `mml_forecast_financial/tests/test_model_fields.py`:
```python
"""
Pure-Python structural tests — verify field definitions without Odoo.
Run: pytest mml_forecast_financial/tests/test_model_fields.py -q
"""
import importlib
import sys

# Stubs are installed by conftest.py at collection time.


def _import_model(module_path):
    """Import a model module, resolving its full dotted path."""
    return importlib.import_module(module_path)


class TestProductTemplateExt:
    def test_x_cbm_per_unit_field_defined(self):
        mod = _import_model('mml_forecast_core.models.product_template_ext')
        cls = mod.ProductTemplateForecasting
        assert 'x_cbm_per_unit' in cls._fields_meta

    def test_x_3pl_pick_rate_field_defined(self):
        mod = _import_model('mml_forecast_core.models.product_template_ext')
        cls = mod.ProductTemplateForecasting
        assert 'x_3pl_pick_rate' in cls._fields_meta
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /e/ClaudeCode/projects/mml.odoo/mml.odoo.apps/mml.forecasting
pytest mml_forecast_financial/tests/test_model_fields.py::TestProductTemplateExt -q
```
Expected: `ModuleNotFoundError` or `AttributeError` — file doesn't exist yet.

- [ ] **Step 3: Create `mml_forecast_core/models/product_template_ext.py`**

```python
from odoo import models, fields


class ProductTemplateForecasting(models.Model):
    _inherit = 'product.template'

    x_cbm_per_unit = fields.Float(
        string='CBM per Unit',
        digits=(12, 6),
        help='Cubic metres per unit. Used to calculate freight cost in forecasts.',
    )
    x_3pl_pick_rate = fields.Float(
        string='3PL Pick Rate (NZD/unit)',
        digits=(12, 4),
        help='Mainfreight pick/pack/despatch cost per unit. Used in COGS waterfall.',
    )
```

- [ ] **Step 4: Add import to `mml_forecast_core/models/__init__.py`**

Existing file ends with:
```python
from . import forecast_config
```
Add after that line:
```python
from . import product_template_ext
```

- [ ] **Step 5: Create `mml_forecast_core/views/product_template_ext_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Forecasting tab on product.template form -->
    <record id="view_product_template_form_forecasting" model="ir.ui.view">
        <field name="name">product.template.form.forecasting</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_only_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//notebook" position="inside">
                <page string="Forecasting" name="forecasting_tab">
                    <group string="Cost Drivers">
                        <field name="x_cbm_per_unit"/>
                        <field name="x_3pl_pick_rate"/>
                    </group>
                </page>
            </xpath>
        </field>
    </record>

</odoo>
```

- [ ] **Step 6: Add view to `mml_forecast_core/__manifest__.py` data[]**

In `mml_forecast_core/__manifest__.py`, find the `'data': [` block and add the new XML file. The existing entries in data[] are for core views. Add:
```python
'views/product_template_ext_views.xml',
```
after the existing view XML entries (before the closing `]`).

- [ ] **Step 7: Run test to confirm it passes**

```bash
cd /e/ClaudeCode/projects/mml.odoo/mml.odoo.apps/mml.forecasting
pytest mml_forecast_financial/tests/test_model_fields.py::TestProductTemplateExt -q
```
Expected: `2 passed`

- [ ] **Step 8: Commit**

```bash
cd /e/ClaudeCode/projects/mml.odoo/mml.odoo.apps/mml.forecasting
git add mml_forecast_core/models/product_template_ext.py \
        mml_forecast_core/models/__init__.py \
        mml_forecast_core/views/product_template_ext_views.xml \
        mml_forecast_core/__manifest__.py \
        mml_forecast_financial/tests/__init__.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: add x_cbm_per_unit and x_3pl_pick_rate to product.template"
```

---

### Task 2: Split `payments_fob` into deposit + balance on `forecast.cashflow.line`

**Files:**
- Modify: `mml_forecast_financial/models/forecast_cashflow_line.py`

- [ ] **Step 1: Add structural tests for the new fields**

Append to `mml_forecast_financial/tests/test_model_fields.py`:
```python
class TestCashflowLineFobSplit:
    def test_payments_fob_deposit_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_cashflow_line')
        cls = mod.ForecastCashflowLine
        assert 'payments_fob_deposit' in cls._fields_meta

    def test_payments_fob_balance_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_cashflow_line')
        cls = mod.ForecastCashflowLine
        assert 'payments_fob_balance' in cls._fields_meta
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestCashflowLineFobSplit -q
```
Expected: `AttributeError: type object 'ForecastCashflowLine' has no attribute '_fields_meta'` or `AssertionError`.

- [ ] **Step 3: Modify `forecast_cashflow_line.py`**

Replace the `payments_fob` field and `_compute_cashflow` method:

**Before** (lines 25–71 of current file):
```python
    # --- Outflows ---
    payments_fob = fields.Float(
        string='FOB Payments (NZD)',
        help='Supplier payments (deposit + balance on shipment).',
    )
```

**After** — replace `payments_fob` definition and update `@api.depends`:
```python
    # --- Outflows ---
    payments_fob_deposit = fields.Float(
        string='FOB Deposit (NZD)',
        help='Deposit paid at PO placement (% of FOB, timed months before sale month).',
    )
    payments_fob_balance = fields.Float(
        string='FOB Balance (NZD)',
        help='Balance payment at bill of lading (remainder of FOB, timed by transit days).',
    )
    payments_fob = fields.Float(
        string='FOB Payments (NZD)',
        compute='_compute_payments_fob',
        store=True,
        help='Total FOB payments = deposit + balance.',
    )
```

Replace the `@api.depends` decorator and `_compute_cashflow` signature:
```python
    @api.depends('payments_fob_deposit', 'payments_fob_balance')
    def _compute_payments_fob(self):
        for rec in self:
            rec.payments_fob = rec.payments_fob_deposit + rec.payments_fob_balance

    @api.depends(
        'receipts_from_customers',
        'payments_fob_deposit', 'payments_fob_balance',
        'payments_freight', 'payments_duty_gst',
        'payments_3pl', 'payments_opex',
    )
    def _compute_cashflow(self):
        for rec in self:
            rec.total_outflows = (
                rec.payments_fob
                + rec.payments_freight
                + rec.payments_duty_gst
                + rec.payments_3pl
                + rec.payments_opex
            )
            rec.net_cashflow = rec.receipts_from_customers - rec.total_outflows
```

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestCashflowLineFobSplit -q
```
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add mml_forecast_financial/models/forecast_cashflow_line.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: split payments_fob into deposit and balance on cashflow line"
```

---

### Task 3: Add `receipt_month` to revenue line, `supplier_id` to COGS line

**Files:**
- Modify: `mml_forecast_financial/models/forecast_revenue_line.py`
- Modify: `mml_forecast_financial/models/forecast_cogs_line.py`

- [ ] **Step 1: Add structural tests**

Append to `mml_forecast_financial/tests/test_model_fields.py`:
```python
class TestRevenueLineReceiptMonth:
    def test_receipt_month_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_revenue_line')
        cls = mod.ForecastRevenueLine
        assert 'receipt_month' in cls._fields_meta


class TestCogsLineSupplier:
    def test_supplier_id_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_cogs_line')
        cls = mod.ForecastCogsLine
        assert 'supplier_id' in cls._fields_meta
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestRevenueLineReceiptMonth \
       mml_forecast_financial/tests/test_model_fields.py::TestCogsLineSupplier -q
```
Expected: `2 failed`

- [ ] **Step 3: Add `receipt_month` to `forecast_revenue_line.py`**

After the `revenue` field definition (after line 43), add:
```python
    receipt_month = fields.Date(
        string='Receipt Month',
        help='First day of the month in which this revenue is expected to be received by the customer. '
             'Computed from forecast.customer.term at generation time.',
    )
```

- [ ] **Step 4: Add `supplier_id` to `forecast_cogs_line.py`**

After the `category` field (after `category = fields.Char(...)`, around line 28), add:
```python
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        help='Primary supplier for this product. Used to look up supplier payment terms.',
    )
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestRevenueLineReceiptMonth \
       mml_forecast_financial/tests/test_model_fields.py::TestCogsLineSupplier -q
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add mml_forecast_financial/models/forecast_revenue_line.py \
        mml_forecast_financial/models/forecast_cogs_line.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: add receipt_month to revenue line and supplier_id to COGS line"
```

---

## Chunk 2: New Models

### Task 4: `forecast.opening.balance` — new model

**Files:**
- Create: `mml_forecast_financial/models/forecast_opening_balance.py`
- Modify: `mml_forecast_financial/models/__init__.py`

- [ ] **Step 1: Write pure-Python BS helper tests**

Create `mml_forecast_financial/tests/test_bs_helpers.py`:
```python
"""
Pure-Python tests for BS computation helpers.
These helpers are extracted as module-level functions so they can be tested
without Odoo. The wizard calls these functions internally.

Run: pytest mml_forecast_financial/tests/test_bs_helpers.py -q
"""
from mml_forecast_financial.models.forecast_opening_balance import effective_value


class TestEffectiveValue:
    def test_returns_auto_when_override_false(self):
        assert effective_value(auto=10_000.0, manual=99_000.0, override=False) == 10_000.0

    def test_returns_manual_when_override_true(self):
        assert effective_value(auto=10_000.0, manual=99_000.0, override=True) == 99_000.0

    def test_zero_auto_no_override(self):
        assert effective_value(auto=0.0, manual=5_000.0, override=False) == 0.0

    def test_zero_manual_with_override(self):
        assert effective_value(auto=8_000.0, manual=0.0, override=True) == 0.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/test_bs_helpers.py -q
```
Expected: `ImportError: cannot import name 'effective_value'`

- [ ] **Step 3: Create `forecast_opening_balance.py`**

```python
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
          equity      -> equity, equity_unaffected (+ residual income/expense)
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
```

- [ ] **Step 4: Add structural test for the new model**

Append to `test_model_fields.py`:
```python
class TestForecastOpeningBalance:
    def test_all_auto_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_opening_balance')
        cls = mod.ForecastOpeningBalance
        for item in ('cash', 'receivables', 'inventory', 'payables', 'equity'):
            assert f'opening_{item}' in cls._fields_meta, f'missing opening_{item}'
            assert f'override_{item}' in cls._fields_meta, f'missing override_{item}'
            assert f'effective_{item}' in cls._fields_meta, f'missing effective_{item}'
```

- [ ] **Step 5: Add import to `models/__init__.py`**

Append to `mml_forecast_financial/models/__init__.py`:
```python
from . import forecast_opening_balance
```

- [ ] **Step 6: Run all tests**

```bash
pytest mml_forecast_financial/tests/ -q
```
Expected: `test_bs_helpers.py::TestEffectiveValue` — 4 passed; structural tests — all passed.

- [ ] **Step 7: Commit**

```bash
git add mml_forecast_financial/models/forecast_opening_balance.py \
        mml_forecast_financial/models/__init__.py \
        mml_forecast_financial/tests/test_bs_helpers.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: add forecast.opening.balance model with effective override pattern"
```

---

### Task 5: `forecast.balance.sheet.line` — new model

**Files:**
- Create: `mml_forecast_financial/models/forecast_balance_sheet_line.py`
- Modify: `mml_forecast_financial/models/__init__.py`

- [ ] **Step 1: Add structural test**

Append to `test_model_fields.py`:
```python
class TestForecastBalanceSheetLine:
    def test_base_stored_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_balance_sheet_line')
        cls = mod.ForecastBalanceSheetLine
        for f in ('cash', 'trade_receivables', 'inventory_value',
                  'trade_payables', 'retained_earnings'):
            assert f in cls._fields_meta, f'missing {f}'

    def test_computed_summary_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_balance_sheet_line')
        cls = mod.ForecastBalanceSheetLine
        for f in ('total_current_assets', 'total_current_liabilities',
                  'total_equity', 'total_assets', 'bs_difference'):
            assert f in cls._fields_meta, f'missing {f}'
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestForecastBalanceSheetLine -q
```
Expected: `ImportError`

- [ ] **Step 3: Create `forecast_balance_sheet_line.py`**

```python
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
             'Displayed in red if > 1% of total assets.',
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
```

- [ ] **Step 4: Add import**

Append to `mml_forecast_financial/models/__init__.py`:
```python
from . import forecast_balance_sheet_line
```

- [ ] **Step 5: Run tests**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestForecastBalanceSheetLine -q
```
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add mml_forecast_financial/models/forecast_balance_sheet_line.py \
        mml_forecast_financial/models/__init__.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: add forecast.balance.sheet.line model"
```

---

### Task 6: `forecast.variance.line` + P&L actuals fields

**Files:**
- Create: `mml_forecast_financial/models/forecast_variance_line.py`
- Modify: `mml_forecast_financial/models/forecast_pnl_line.py`
- Modify: `mml_forecast_financial/models/__init__.py`

- [ ] **Step 1: Add structural tests + variance math tests**

Append to `test_model_fields.py`:
```python
class TestForecastVarianceLine:
    def test_variance_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_variance_line')
        cls = mod.ForecastVarianceLine
        for f in ('forecast_units', 'forecast_revenue', 'actual_units',
                  'actual_revenue', 'variance_units', 'variance_revenue',
                  'variance_revenue_pct'):
            assert f in cls._fields_meta, f'missing {f}'


class TestPnlLineActualFields:
    def test_actual_stored_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_pnl_line')
        cls = mod.ForecastPnlLine
        for f in ('actual_revenue', 'actual_cogs', 'actual_opex'):
            assert f in cls._fields_meta, f'missing {f}'
```

Add variance math tests to `test_bs_helpers.py`:
```python
from mml_forecast_financial.models.forecast_variance_line import variance_pct


class TestVariancePct:
    def test_positive_variance(self):
        assert variance_pct(actual=120.0, forecast=100.0) == 20.0

    def test_negative_variance(self):
        assert variance_pct(actual=80.0, forecast=100.0) == -20.0

    def test_zero_forecast_returns_zero(self):
        assert variance_pct(actual=50.0, forecast=0.0) == 0.0

    def test_zero_actual_zero_forecast(self):
        assert variance_pct(actual=0.0, forecast=0.0) == 0.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/ -q
```
Expected: `ImportError` on `forecast_variance_line`

- [ ] **Step 3: Create `forecast_variance_line.py`**

```python
from odoo import models, fields, api


# --- Pure-Python helper ---

def variance_pct(actual, forecast):
    """Compute variance percentage. Returns 0.0 if forecast is zero."""
    if not forecast:
        return 0.0
    return (actual - forecast) / forecast * 100.0


class ForecastVarianceLine(models.Model):
    _name = 'forecast.variance.line'
    _description = 'Forecast vs Actual Variance Line'
    _order = 'period_start, product_id, partner_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # Dimensions
    product_id = fields.Many2one('product.product', string='Product')
    partner_id = fields.Many2one('res.partner', string='Customer')
    brand = fields.Char(string='Brand')
    category = fields.Char(string='Category')

    # Forecast values (from forecast.revenue.line)
    forecast_units = fields.Float(string='Forecast Units', digits=(12, 2))
    forecast_revenue = fields.Float(string='Forecast Revenue (NZD)', digits=(16, 2))

    # Actual values (from sale.order.line)
    actual_units = fields.Float(string='Actual Units', digits=(12, 2))
    actual_revenue = fields.Float(string='Actual Revenue (NZD)', digits=(16, 2))

    # Computed variances
    variance_units = fields.Float(
        string='Variance Units',
        compute='_compute_variance',
        digits=(12, 2),
    )
    variance_revenue = fields.Float(
        string='Variance Revenue (NZD)',
        compute='_compute_variance',
        digits=(16, 2),
    )
    variance_revenue_pct = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        digits=(5, 2),
        help='Positive = actual beat forecast.',
    )

    @api.depends('actual_units', 'forecast_units', 'actual_revenue', 'forecast_revenue')
    def _compute_variance(self):
        for rec in self:
            rec.variance_units = rec.actual_units - rec.forecast_units
            rec.variance_revenue = rec.actual_revenue - rec.forecast_revenue
            rec.variance_revenue_pct = variance_pct(rec.actual_revenue, rec.forecast_revenue)
```

- [ ] **Step 4: Add actuals + variance fields to `forecast_pnl_line.py`**

After the `ebitda_pct` field definition and before `@api.depends`, add:
```python
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
```

Add new compute method after `_compute_margins`:
```python
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
```

- [ ] **Step 5: Add import**

Append to `mml_forecast_financial/models/__init__.py`:
```python
from . import forecast_variance_line
```

- [ ] **Step 6: Run all tests**

```bash
pytest mml_forecast_financial/tests/ -q
```
Expected: all passed (no failures)

- [ ] **Step 7: Commit**

```bash
git add mml_forecast_financial/models/forecast_variance_line.py \
        mml_forecast_financial/models/forecast_pnl_line.py \
        mml_forecast_financial/models/__init__.py \
        mml_forecast_financial/tests/test_model_fields.py \
        mml_forecast_financial/tests/test_bs_helpers.py
git commit -m "feat: add forecast.variance.line model and P&L actuals/variance fields"
```

---

## Chunk 3: Wizard — Pipeline Rewrite

### Task 7: Per-supplier timing fix + full pipeline update in wizard

**Files:**
- Modify: `mml_forecast_financial/wizards/forecast_generate_wizard.py`

This is the largest task. Make all wizard changes in one go and test with integration tests only (the wizard depends on `self.env` throughout).

- [ ] **Step 1: Extend `_get_supplier_info()` to return `partner_id`**

Current method (around line 292):
```python
    def _get_supplier_info(self, product):
        """Get primary supplier price and currency for a product."""
        info = product.seller_ids.sorted('sequence')[:1]
        if info:
            return {
                'price': info.price,
                'currency': info.currency_id.name if info.currency_id else 'NZD',
            }
        return {'price': 0.0, 'currency': 'NZD'}
```

Replace with:
```python
    def _get_supplier_info(self, product):
        """Get primary supplier price, currency, and partner_id for a product."""
        info = product.seller_ids.sorted('sequence')[:1]
        if info:
            return {
                'price': info.price,
                'currency': info.currency_id.name if info.currency_id else 'NZD',
                'partner_id': info.partner_id.id if info.partner_id else False,
            }
        return {'price': 0.0, 'currency': 'NZD', 'partner_id': False}
```

- [ ] **Step 2: Add `supplier_id` write in `_generate_cogs_lines()`**

In `_generate_cogs_lines()`, the `_get_supplier_info()` call returns `supplier_info`. Add `supplier_id` to `lines_data.append({...})`:

After `'tpl_pick_rate': tpl_rate,`, add:
```python
                'supplier_id': supplier_info.get('partner_id', False),
```

- [ ] **Step 3: Add `receipt_month` write in `_generate_revenue_lines()`**

In `_generate_revenue_lines()`, add a `CustomerTerm` reference and `receipt_month` computation:

At the top of the method, after `RevenueLine = self.env['forecast.revenue.line']`, add:
```python
        CustomerTerm = self.env['forecast.customer.term']
```

In `lines_data.append({...})`, after computing `sell_price`, compute `receipt_month`:
```python
            receipt_date = CustomerTerm.get_default_receipt_date(
                config, d['partner_id'], d['period_start'],
            )
            receipt_month = receipt_date.replace(day=1)
```

Add to `lines_data.append({...})`:
```python
                'receipt_month': receipt_month,
```

- [ ] **Step 4: Fix per-supplier timing in `_generate_cashflow_lines()`**

Replace the supplier term resolution block (lines 381–394 in the original):

**Remove** this block:
```python
        # --- Resolve supplier payment timing parameters ---
        supplier_terms = config.supplier_term_ids
        if supplier_terms:
            # Use the first configured supplier term.
            # Future: loop over terms if supplier_id is on cogs lines.
            s_term = supplier_terms[0]
            deposit_months_back = math.ceil(s_term.deposit_trigger_days / 30.0)
            transit_months_back = math.ceil(s_term.transit_days / 30.0)
            deposit_pct = s_term.deposit_pct / 100.0
        else:
            # Default NZ import assumptions: ~90-day total lead → 3-month deposit,
            # ~22-day transit → 1-month balance.
            deposit_months_back = 3
            transit_months_back = 1
            deposit_pct = 0.30

        balance_pct = 1.0 - deposit_pct
```

**Replace with:**
```python
        # --- Build per-supplier term lookup ---
        # Falls back to NZ import defaults when a product's supplier is not in the term list.
        _DEFAULT_DEPOSIT_MONTHS = 3
        _DEFAULT_TRANSIT_MONTHS = 1
        _DEFAULT_DEPOSIT_PCT = 0.30

        supplier_term_map = {
            term.supplier_id.id: term
            for term in config.supplier_term_ids
            if term.supplier_id
        }
```

**Replace** the cogs iteration loop (currently loops with a single set of timing vars). Replace:
```python
        for cogs in cogs_lines:
            sale_month = cogs.period_start
            if sale_month not in month_set:
                continue

            fob = cogs.fob_total_nzd
            freight = cogs.freight_total_nzd
            duty = cogs.duty_total_nzd

            # Deposit payment: ceil(deposit_trigger_days/30) months before sale
            deposit_month = (
                sale_month - relativedelta(months=deposit_months_back)
            ).replace(day=1)
            if deposit_month in month_set:
                fob_deposit_by_month[deposit_month] += fob * deposit_pct

            # Balance payment: ceil(transit_days/30) months before sale
            balance_month = (
                sale_month - relativedelta(months=transit_months_back)
            ).replace(day=1)
            if balance_month in month_set:
                fob_balance_by_month[balance_month] += fob * balance_pct
                # Freight paid same month as balance (forwarder invoices at shipment)
                freight_by_month[balance_month] += freight

            # GST/duty: paid on arrival, which aligns with the sale month
            # CIF = FOB + freight; GST is levied on CIF value.
            cif = fob + freight
            gst_on_import = cif * tax_rate
            if sale_month in month_set:
                duty_gst_by_month[sale_month] += duty + gst_on_import

            # 3PL: pick/pack/despatch costs incurred in the sale month
            if sale_month in month_set:
                tpl_by_month[sale_month] += cogs.tpl_total_nzd
```

With:
```python
        for cogs in cogs_lines:
            sale_month = cogs.period_start
            if sale_month not in month_set:
                continue

            fob = cogs.fob_total_nzd
            freight = cogs.freight_total_nzd
            duty = cogs.duty_total_nzd

            # Resolve per-supplier timing
            s_term = supplier_term_map.get(cogs.supplier_id.id if cogs.supplier_id else None)
            if s_term:
                deposit_months_back = math.ceil(s_term.deposit_trigger_days / 30.0)
                transit_months_back = math.ceil(s_term.transit_days / 30.0)
                deposit_pct = s_term.deposit_pct / 100.0
            else:
                deposit_months_back = _DEFAULT_DEPOSIT_MONTHS
                transit_months_back = _DEFAULT_TRANSIT_MONTHS
                deposit_pct = _DEFAULT_DEPOSIT_PCT
            balance_pct = 1.0 - deposit_pct

            # Deposit payment
            deposit_month = (
                sale_month - relativedelta(months=deposit_months_back)
            ).replace(day=1)
            if deposit_month in month_set:
                fob_deposit_by_month[deposit_month] += fob * deposit_pct

            # Balance payment
            balance_month = (
                sale_month - relativedelta(months=transit_months_back)
            ).replace(day=1)
            if balance_month in month_set:
                fob_balance_by_month[balance_month] += fob * balance_pct
                freight_by_month[balance_month] += freight

            # Duty + GST on arrival (sale month)
            cif = fob + freight
            gst_on_import = cif * tax_rate
            if sale_month in month_set:
                duty_gst_by_month[sale_month] += duty + gst_on_import

            # 3PL in sale month
            if sale_month in month_set:
                tpl_by_month[sale_month] += cogs.tpl_total_nzd
```

- [ ] **Step 5: Replace `payments_fob` write with `payments_fob_deposit` + `payments_fob_balance`**

In `_generate_cashflow_lines()`, find the `lines_data.append({...})` block and replace:
```python
            # Aggregate FOB deposit + balance into payments_fob
            payments_fob = (
                fob_deposit_by_month.get(period_start, 0.0)
                + fob_balance_by_month.get(period_start, 0.0)
            )
```

Remove that aggregation and update the dict to write the two fields directly:
```python
                'payments_fob_deposit': fob_deposit_by_month.get(period_start, 0.0),
                'payments_fob_balance': fob_balance_by_month.get(period_start, 0.0),
```

Remove the `'payments_fob': payments_fob,` line from `lines_data.append({...})`.

Also update `_generate_cashflow_lines()` docstring — remove "Future: loop over terms if supplier_id is on cogs lines." comment.

- [ ] **Step 6: Remove the duplicate `receipt_month` computation from `_generate_cashflow_lines()`**

In `_generate_cashflow_lines()`, replace the receivables bucket computation:

**Remove:**
```python
        # --- Receivables: bucket revenue by customer receipt month ---
        receipts_by_month = defaultdict(float)
        for rev in revenue_lines:
            invoice_date = rev.period_start  # treat 1st of month as invoice date
            receipt_date = CustomerTerm.get_default_receipt_date(
                config, rev.partner_id.id, invoice_date,
            )
            receipt_month = receipt_date.replace(day=1)
            if receipt_month in month_set:
                receipts_by_month[receipt_month] += rev.revenue
```

**Replace with** (read `receipt_month` from the now-populated revenue line field):
```python
        # --- Receivables: bucket revenue by customer receipt month ---
        # receipt_month is populated on revenue lines during _generate_revenue_lines()
        receipts_by_month = defaultdict(float)
        for rev in revenue_lines:
            receipt_month = rev.receipt_month
            if receipt_month and receipt_month in month_set:
                receipts_by_month[receipt_month] += rev.revenue
```

Also remove the `CustomerTerm = self.env['forecast.customer.term']` line from `_generate_cashflow_lines()` if it exists (it was used for the now-removed computation).

- [ ] **Step 7: Add `_generate_balance_sheet_lines()` method to wizard**

Add this new method after `_generate_cashflow_lines()`:

```python
    # -------------------------------------------------------------------------
    # Balance Sheet generation
    # -------------------------------------------------------------------------
    def _generate_balance_sheet_lines(self, config, months):
        """
        Build monthly balance sheet snapshots from opening balance + P&L + cashflow.

        Requires cumulative_cashflow to be set on all cashflow lines before calling.
        Calls flush_model() to ensure the DB is current.
        """
        self.env['forecast.cashflow.line'].flush_model()

        ob = config.opening_balance_ids[:1]
        if not ob:
            _logger.warning(
                'No opening balance on config %s — BS lines will use zero opening values',
                config.id,
            )

        inventory = ob.effective_inventory if ob else 0.0
        cumulative_ebitda = 0.0
        cashflow_by_month = {line.period_start: line for line in config.cashflow_line_ids}
        pnl_by_month = {line.period_start: line for line in config.pnl_line_ids}
        revenue_lines = config.revenue_line_ids

        # Pre-compute future FOB balance by month (for trade payables)
        # O(n^2) — acceptable at 12-24 month horizons.
        future_fob_balance = {
            m[0]: sum(
                line.payments_fob_balance
                for line in config.cashflow_line_ids
                if line.period_start > m[0]
            )
            for m in months
        }

        lines_data = []
        for period_start, period_label in months:
            cf = cashflow_by_month.get(period_start)
            pnl = pnl_by_month.get(period_start)

            cash = (ob.effective_cash if ob else 0.0) + (cf.cumulative_cashflow if cf else 0.0)

            trade_receivables = sum(
                r.revenue for r in revenue_lines
                if r.period_start <= period_start
                and r.receipt_month
                and r.receipt_month > period_start
            )

            fob_received = cf.payments_fob_balance if cf else 0.0
            total_cogs = pnl.total_cogs if pnl else 0.0
            inventory += fob_received - total_cogs

            trade_payables = future_fob_balance.get(period_start, 0.0)
            cumulative_ebitda += pnl.ebitda if pnl else 0.0
            retained_earnings = (ob.effective_equity if ob else 0.0) + cumulative_ebitda

            lines_data.append({
                'config_id': config.id,
                'period_start': period_start,
                'period_label': period_label,
                'cash': cash,
                'trade_receivables': trade_receivables,
                'inventory_value': inventory,
                'trade_payables': trade_payables,
                'retained_earnings': retained_earnings,
            })

        lines = self.env['forecast.balance.sheet.line'].create(lines_data)
        _logger.info('Created %d balance sheet lines', len(lines))
        return lines
```

- [ ] **Step 8: Add `_compute_variance_lines()` method to wizard**

Add after `_generate_balance_sheet_lines()`:

```python
    # -------------------------------------------------------------------------
    # Variance computation
    # -------------------------------------------------------------------------
    def _compute_variance_lines(self, config, months):
        """
        Compute forecast vs actual variance for past periods.

        Pass 1: Product-level variance lines (forecast.variance.line).
        Pass 2: P&L summary actuals (actual_revenue, actual_cogs, actual_opex on forecast.pnl.line).

        Only processes months where period_start < date.today().
        Silently skips if all periods are in the future.
        """
        from datetime import date
        today = date.today()
        past_months = [(ps, pl) for ps, pl in months if ps < today]
        if not past_months:
            _logger.info('All forecast periods are in the future — skipping variance computation')
            return

        SaleOrderLine = self.env['sale.order.line']
        AccountMoveLine = self.env['account.move.line']
        VarianceLine = self.env['forecast.variance.line']

        # Unlink existing variance lines for this config before recomputing
        config.variance_line_ids.unlink()

        # --- Pass 1: Product-level variance ---
        for period_start, period_label in past_months:
            period_end = period_start + relativedelta(months=1)

            actual_sol = SaleOrderLine.search([
                ('order_id.state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', period_start),
                ('order_id.date_order', '<', period_end),
            ])

            # Group actuals by (product_id, partner_id)
            actual_by_key = defaultdict(lambda: {'units': 0.0, 'revenue': 0.0})
            for sol in actual_sol:
                key = (sol.product_id.id, sol.order_id.partner_id.id)
                actual_by_key[key]['units'] += sol.product_uom_qty
                actual_by_key[key]['revenue'] += sol.price_subtotal

            # Match against forecast revenue lines
            forecast_lines = config.revenue_line_ids.filtered(
                lambda r: r.period_start == period_start
            )

            # Build variance lines — one per (product, partner) in forecast
            lines_data = []
            for rev in forecast_lines:
                key = (rev.product_id.id, rev.partner_id.id)
                actuals = actual_by_key.get(key, {})
                lines_data.append({
                    'config_id': config.id,
                    'period_start': period_start,
                    'period_label': period_label,
                    'product_id': rev.product_id.id,
                    'partner_id': rev.partner_id.id,
                    'brand': rev.brand,
                    'category': rev.category,
                    'forecast_units': rev.forecast_units,
                    'forecast_revenue': rev.revenue,
                    'actual_units': actuals.get('units', 0.0),
                    'actual_revenue': actuals.get('revenue', 0.0),
                })

            if lines_data:
                VarianceLine.create(lines_data)

        # --- Pass 2: P&L summary actuals ---
        for pnl_line in config.pnl_line_ids.filtered(lambda l: l.period_start < today):
            period_end = pnl_line.period_start + relativedelta(months=1)

            aml = AccountMoveLine.search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', pnl_line.period_start),
                ('date', '<', period_end),
                ('company_id', '=', config.company_id.id),
            ])

            pnl_line.write({
                'actual_revenue': sum(
                    line.balance for line in aml
                    if line.account_id.account_type in ('income', 'income_other')
                ),
                'actual_cogs': abs(sum(
                    line.balance for line in aml
                    if line.account_id.account_type == 'expense_direct_cost'
                )),
                'actual_opex': abs(sum(
                    line.balance for line in aml
                    if line.account_id.account_type == 'expense'
                )),
            })

        _logger.info(
            'Computed variance for %d past periods on config %s',
            len(past_months), config.id,
        )
```

- [ ] **Step 9: Update `generate()` — add unlinks + new pipeline steps**

In `generate(config)`, replace the unlink block:
```python
        # Clear previous generated data
        config.revenue_line_ids.unlink()
        config.cogs_line_ids.unlink()
        config.pnl_line_ids.unlink()
        config.cashflow_line_ids.unlink()
```

With:
```python
        # Clear previous generated data
        config.revenue_line_ids.unlink()
        config.cogs_line_ids.unlink()
        config.pnl_line_ids.unlink()
        config.cashflow_line_ids.unlink()
        config.balance_sheet_line_ids.unlink()
        # Note: variance_line_ids are NOT unlinked here — _compute_variance_lines()
        # unlinks them internally so they are cleared correctly on both full
        # regeneration and standalone action_compute_variance() calls.
```

Replace the pipeline call block:
```python
        revenue_lines = self._generate_revenue_lines(config, demand)
        cogs_lines = self._generate_cogs_lines(config, demand)
        self._generate_pnl_lines(config, months, revenue_lines, cogs_lines)
        self._generate_cashflow_lines(config, months, revenue_lines, cogs_lines)
```

With:
```python
        revenue_lines = self._generate_revenue_lines(config, demand)
        cogs_lines = self._generate_cogs_lines(config, demand)
        self._generate_pnl_lines(config, months, revenue_lines, cogs_lines)
        self._generate_cashflow_lines(config, months, revenue_lines, cogs_lines)
        self._generate_balance_sheet_lines(config, months)
        self._compute_variance_lines(config, months)
```

Update the docstring to list all 8 pipeline steps:
```python
        """
        Main forecast generation pipeline.

        Steps:
            1. Build month buckets
            2. Pull demand forecast (ROQ or sale history)
            3. Build revenue lines (with receipt_month)
            4. Build COGS waterfall lines (with supplier_id)
            5. Aggregate to P&L summary
            6. Compute cash flow timing (per-supplier)
            7. Build balance sheet lines
            8. Compute variance (past periods only)
        """
```

- [ ] **Step 10: Write pure-Python per-supplier timing test**

The per-supplier timing lookup is pure Python. Extract a test by calling the logic directly with mock-like inputs.

Create `mml_forecast_financial/tests/test_per_supplier_timing.py`:
```python
"""
Pure-Python tests for per-supplier cashflow timing logic.
Tests the supplier_term_map lookup and fallback behaviour used in
_generate_cashflow_lines(). The supplier term lookup is extracted here
as a standalone function test — the wizard logic mirrors this exactly.

Run: pytest mml_forecast_financial/tests/test_per_supplier_timing.py -q
"""
import math


_DEFAULT_DEPOSIT_MONTHS = 3
_DEFAULT_TRANSIT_MONTHS = 1
_DEFAULT_DEPOSIT_PCT = 0.30


def resolve_supplier_timing(supplier_id, supplier_term_map):
    """
    Mirror of the per-supplier timing resolution in _generate_cashflow_lines().
    Returns (deposit_months_back, transit_months_back, deposit_pct).
    """
    term = supplier_term_map.get(supplier_id)
    if term:
        return (
            math.ceil(term['deposit_trigger_days'] / 30.0),
            math.ceil(term['transit_days'] / 30.0),
            term['deposit_pct'] / 100.0,
        )
    return (_DEFAULT_DEPOSIT_MONTHS, _DEFAULT_TRANSIT_MONTHS, _DEFAULT_DEPOSIT_PCT)


class TestPerSupplierTiming:
    def _make_term(self, deposit_days, transit_days, deposit_pct):
        return {
            'deposit_trigger_days': deposit_days,
            'transit_days': transit_days,
            'deposit_pct': deposit_pct,
        }

    def test_known_supplier_uses_its_term(self):
        supplier_id = 42
        term_map = {42: self._make_term(60, 22, 30)}
        dep, trans, pct = resolve_supplier_timing(supplier_id, term_map)
        assert dep == 2   # ceil(60/30)
        assert trans == 1  # ceil(22/30)
        assert pct == 0.30

    def test_different_supplier_long_lead(self):
        supplier_id = 7
        term_map = {7: self._make_term(90, 45, 40)}
        dep, trans, pct = resolve_supplier_timing(supplier_id, term_map)
        assert dep == 3   # ceil(90/30)
        assert trans == 2  # ceil(45/30)
        assert pct == 0.40

    def test_unknown_supplier_uses_defaults(self):
        dep, trans, pct = resolve_supplier_timing(99, {})
        assert dep == _DEFAULT_DEPOSIT_MONTHS
        assert trans == _DEFAULT_TRANSIT_MONTHS
        assert pct == _DEFAULT_DEPOSIT_PCT

    def test_none_supplier_id_uses_defaults(self):
        dep, trans, pct = resolve_supplier_timing(None, {42: self._make_term(60, 22, 30)})
        assert dep == _DEFAULT_DEPOSIT_MONTHS

    def test_deposit_and_balance_pct_sum_to_one(self):
        supplier_id = 5
        term_map = {5: self._make_term(75, 30, 35)}
        dep, trans, deposit_pct = resolve_supplier_timing(supplier_id, term_map)
        balance_pct = 1.0 - deposit_pct
        assert abs(deposit_pct + balance_pct - 1.0) < 1e-9
```

- [ ] **Step 11: Run all pure-Python tests**

```bash
cd /e/ClaudeCode/projects/mml.odoo/mml.odoo.apps/mml.forecasting
pytest mml_forecast_financial/tests/ -m "not odoo_integration" -q
```
Expected: all passed

- [ ] **Step 12: Commit**

```bash
git add mml_forecast_financial/wizards/forecast_generate_wizard.py \
        mml_forecast_financial/tests/test_per_supplier_timing.py
git commit -m "feat: per-supplier timing, receipt_month, BS and variance pipeline steps in wizard"
```

---

### Task 8: `forecast_config_ext.py` — new One2many fields + action methods

**Files:**
- Modify: `mml_forecast_financial/models/forecast_config_ext.py`

- [ ] **Step 1: Add structural test**

Append to `test_model_fields.py`:
```python
class TestConfigExtNewFields:
    def test_opening_balance_ids_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'opening_balance_ids' in cls._fields_meta

    def test_balance_sheet_line_ids_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'balance_sheet_line_ids' in cls._fields_meta

    def test_variance_line_ids_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'variance_line_ids' in cls._fields_meta
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest mml_forecast_financial/tests/test_model_fields.py::TestConfigExtNewFields -q
```
Expected: `3 failed`

- [ ] **Step 3: Update `forecast_config_ext.py`**

Add three new One2many fields after `opex_line_ids`:
```python
    opening_balance_ids = fields.One2many(
        'forecast.opening.balance', 'config_id', string='Opening Balance',
    )
    balance_sheet_line_ids = fields.One2many(
        'forecast.balance.sheet.line', 'config_id', string='Balance Sheet Lines',
    )
    variance_line_ids = fields.One2many(
        'forecast.variance.line', 'config_id', string='Variance Lines',
    )
```

Add two new action methods and override `action_reset_draft` after `_compute_totals`:
```python
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

    def action_compute_variance(self):
        """
        Recompute variance lines and P&L actuals for all past periods.
        Can be called independently of a full forecast regeneration.
        """
        self.ensure_one()
        from dateutil.relativedelta import relativedelta
        months = []
        current = self.date_start.replace(day=1)
        for _ in range(self.horizon_months):
            months.append((current, current.strftime('%Y-%m')))
            current += relativedelta(months=1)
        self.env['forecast.generate.wizard']._compute_variance_lines(self, months)

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
```

- [ ] **Step 4: Run tests**

```bash
pytest mml_forecast_financial/tests/ -q
```
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add mml_forecast_financial/models/forecast_config_ext.py \
        mml_forecast_financial/tests/test_model_fields.py
git commit -m "feat: add opening_balance_ids, balance_sheet_line_ids, variance_line_ids to forecast.config"
```

---

## Chunk 4: Views, Security, Manifest

### Task 9: Update `forecast_financial_views.xml` — config form

**Files:**
- Modify: `mml_forecast_financial/views/forecast_financial_views.xml`

This task only touches XML. No new tests needed — correctness verified by Odoo install.

- [ ] **Step 1: Add header buttons**

In `forecast_financial_views.xml`, find the config form extension `<xpath ...>` and add a new xpath before the tab injection to add header buttons:

```xml
            <!-- Header buttons -->
            <xpath expr="//header" position="inside">
                <button name="action_pull_opening_balance"
                        string="Pull from Accounting"
                        type="object"
                        invisible="state == 'locked'"/>
                <button name="action_compute_variance"
                        string="Compute Variance"
                        type="object"
                        invisible="state != 'generated'"/>
            </xpath>
```

- [ ] **Step 2: Add Opening Balance tab**

Add before the `<!-- Tab: Operating Expenses -->` section:
```xml
                <!-- Tab: Opening Balance -->
                <page string="Opening Balance" name="opening_balance">
                    <p class="text-muted">
                        Auto-pulled from Odoo accounting trial balance at the forecast start date.
                        Toggle Override to enter a manual value — the auto value is still retained.
                    </p>
                    <field name="opening_balance_ids" nolabel="1">
                        <form>
                            <group string="Cash &amp; Receivables">
                                <field name="opening_cash" string="Cash (Auto)" readonly="1"/>
                                <field name="override_cash"/>
                                <field name="opening_cash_manual" string="Cash (Manual)"
                                       invisible="not override_cash"/>
                                <field name="effective_cash" string="Cash (Effective)" readonly="1"/>
                            </group>
                            <group string="Receivables">
                                <field name="opening_receivables" string="Receivables (Auto)" readonly="1"/>
                                <field name="override_receivables"/>
                                <field name="opening_receivables_manual" string="Receivables (Manual)"
                                       invisible="not override_receivables"/>
                                <field name="effective_receivables" string="Receivables (Effective)" readonly="1"/>
                            </group>
                            <group string="Inventory">
                                <field name="opening_inventory" string="Inventory (Auto)" readonly="1"/>
                                <field name="override_inventory"/>
                                <field name="opening_inventory_manual" string="Inventory (Manual)"
                                       invisible="not override_inventory"/>
                                <field name="effective_inventory" string="Inventory (Effective)" readonly="1"/>
                            </group>
                            <group string="Payables">
                                <field name="opening_payables" string="Payables (Auto)" readonly="1"/>
                                <field name="override_payables"/>
                                <field name="opening_payables_manual" string="Payables (Manual)"
                                       invisible="not override_payables"/>
                                <field name="effective_payables" string="Payables (Effective)" readonly="1"/>
                            </group>
                            <group string="Equity">
                                <field name="opening_equity" string="Equity (Auto)" readonly="1"/>
                                <field name="override_equity"/>
                                <field name="opening_equity_manual" string="Equity (Manual)"
                                       invisible="not override_equity"/>
                                <field name="effective_equity" string="Equity (Effective)" readonly="1"/>
                            </group>
                        </form>
                    </field>
                </page>
```

- [ ] **Step 3: Update P&L Summary tab — add actuals + variance columns**

Replace the existing P&L Summary page:
```xml
                <!-- Tab: P&L Summary -->
                <page string="P&amp;L Summary" name="pnl_summary"
                      invisible="state == 'draft'">
                    <field name="pnl_line_ids">
                        <list>
                            <field name="period_label"/>
                            <field name="revenue" widget="monetary"/>
                            <field name="actual_revenue" widget="monetary" optional="show"/>
                            <field name="variance_revenue" widget="monetary" optional="show"/>
                            <field name="variance_revenue_pct" widget="percentage" optional="show"
                                   decoration-success="variance_revenue_pct &gt; 0"
                                   decoration-danger="variance_revenue_pct &lt; -10"/>
                            <field name="total_cogs" widget="monetary"/>
                            <field name="gross_margin" widget="monetary"/>
                            <field name="gross_margin_pct" widget="percentage"/>
                            <field name="total_opex" widget="monetary"/>
                            <field name="ebitda" widget="monetary"/>
                            <field name="actual_ebitda" widget="monetary" optional="show"/>
                            <field name="variance_ebitda_pct" widget="percentage" optional="show"/>
                            <field name="ebitda_pct" widget="percentage"/>
                        </list>
                    </field>
                </page>
```

- [ ] **Step 4: Update Cash Flow tab — split payments_fob columns**

Replace the Cash Flow page:
```xml
                <!-- Tab: Cash Flow -->
                <page string="Cash Flow" name="cashflow"
                      invisible="state == 'draft'">
                    <field name="cashflow_line_ids">
                        <list>
                            <field name="period_label"/>
                            <field name="receipts_from_customers" widget="monetary"/>
                            <field name="payments_fob_deposit" widget="monetary" optional="show"/>
                            <field name="payments_fob_balance" widget="monetary" optional="show"/>
                            <field name="payments_fob" widget="monetary"/>
                            <field name="payments_freight" widget="monetary"/>
                            <field name="payments_duty_gst" widget="monetary"/>
                            <field name="payments_opex" widget="monetary"/>
                            <field name="net_cashflow" widget="monetary"/>
                            <field name="cumulative_cashflow" widget="monetary"/>
                        </list>
                    </field>
                </page>
```

- [ ] **Step 5: Add Balance Sheet tab**

Add after the COGS Detail tab (after the closing `</page>` for cogs_detail):
```xml
                <!-- Tab: Balance Sheet -->
                <page string="Balance Sheet" name="balance_sheet"
                      invisible="state == 'draft'">
                    <field name="balance_sheet_line_ids">
                        <list>
                            <field name="period_label"/>
                            <field name="cash" widget="monetary"/>
                            <field name="trade_receivables" widget="monetary"/>
                            <field name="inventory_value" widget="monetary"/>
                            <field name="total_current_assets" widget="monetary"/>
                            <field name="trade_payables" widget="monetary"/>
                            <field name="retained_earnings" widget="monetary"/>
                            <field name="bs_difference" widget="monetary"
                                   decoration-danger="abs(bs_difference) &gt; total_current_assets * 0.01"/>
                        </list>
                    </field>
                </page>

                <!-- Tab: Variance -->
                <page string="Variance" name="variance"
                      invisible="state == 'draft'">
                    <field name="variance_line_ids">
                        <list>
                            <field name="period_label"/>
                            <field name="product_id"/>
                            <field name="partner_id"/>
                            <field name="forecast_units"/>
                            <field name="actual_units"/>
                            <field name="forecast_revenue" widget="monetary"/>
                            <field name="actual_revenue" widget="monetary"/>
                            <field name="variance_revenue" widget="monetary"/>
                            <field name="variance_revenue_pct" widget="percentage"
                                   decoration-success="variance_revenue_pct &gt; 0"
                                   decoration-danger="variance_revenue_pct &lt; -10"/>
                        </list>
                    </field>
                </page>
```

- [ ] **Step 6: Commit**

```bash
git add mml_forecast_financial/views/forecast_financial_views.xml
git commit -m "feat: update config form with opening balance, BS, variance tabs and new action buttons"
```

---

### Task 10: New standalone views + menu structure

**Files:**
- Create: `mml_forecast_financial/views/forecast_balance_sheet_views.xml`
- Create: `mml_forecast_financial/views/forecast_variance_views.xml`
- Modify: `mml_forecast_financial/views/forecast_financial_views.xml` — update Analysis menus

- [ ] **Step 1: Create `forecast_balance_sheet_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Balance Sheet standalone list view -->
    <record id="view_forecast_balance_sheet_list" model="ir.ui.view">
        <field name="name">forecast.balance.sheet.line.list</field>
        <field name="model">forecast.balance.sheet.line</field>
        <field name="arch" type="xml">
            <list>
                <field name="config_id"/>
                <field name="period_label"/>
                <field name="cash" widget="monetary"/>
                <field name="trade_receivables" widget="monetary"/>
                <field name="inventory_value" widget="monetary"/>
                <field name="total_current_assets" widget="monetary"/>
                <field name="trade_payables" widget="monetary"/>
                <field name="retained_earnings" widget="monetary"/>
                <field name="total_equity" widget="monetary"/>
                <field name="bs_difference" widget="monetary"
                       decoration-danger="abs(bs_difference) &gt; total_current_assets * 0.01"/>
            </list>
        </field>
    </record>

    <record id="action_forecast_balance_sheet" model="ir.actions.act_window">
        <field name="name">Balance Sheet</field>
        <field name="res_model">forecast.balance.sheet.line</field>
        <field name="view_mode">list,form</field>
    </record>

</odoo>
```

- [ ] **Step 2: Create `forecast_variance_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Variance pivot view -->
    <record id="view_forecast_variance_pivot" model="ir.ui.view">
        <field name="name">forecast.variance.line.pivot</field>
        <field name="model">forecast.variance.line</field>
        <field name="arch" type="xml">
            <pivot>
                <field name="brand" type="row"/>
                <field name="product_id" type="row"/>
                <field name="period_label" type="col"/>
                <field name="forecast_revenue" type="measure"/>
                <field name="actual_revenue" type="measure"/>
                <field name="variance_revenue" type="measure"/>
                <field name="variance_revenue_pct" type="measure"/>
            </pivot>
        </field>
    </record>

    <!-- Variance list view -->
    <record id="view_forecast_variance_list" model="ir.ui.view">
        <field name="name">forecast.variance.line.list</field>
        <field name="model">forecast.variance.line</field>
        <field name="arch" type="xml">
            <list>
                <field name="config_id"/>
                <field name="period_label"/>
                <field name="product_id"/>
                <field name="partner_id"/>
                <field name="brand"/>
                <field name="forecast_units"/>
                <field name="actual_units"/>
                <field name="forecast_revenue" widget="monetary"/>
                <field name="actual_revenue" widget="monetary"/>
                <field name="variance_revenue" widget="monetary"/>
                <field name="variance_revenue_pct" widget="percentage"
                       decoration-success="variance_revenue_pct &gt; 0"
                       decoration-danger="variance_revenue_pct &lt; -10"/>
            </list>
        </field>
    </record>

    <record id="action_forecast_variance" model="ir.actions.act_window">
        <field name="name">Variance</field>
        <field name="res_model">forecast.variance.line</field>
        <field name="view_mode">pivot,list</field>
    </record>

</odoo>
```

- [ ] **Step 3: Add P&L pivot view to `forecast_financial_views.xml`**

The existing `action_forecast_pnl` action is `list,form`. Add a pivot view and update the action to include pivot mode. Find the `action_forecast_pnl` record and replace it:

```xml
    <!-- P&L pivot view for standalone analysis -->
    <record id="view_forecast_pnl_pivot" model="ir.ui.view">
        <field name="name">forecast.pnl.line.pivot</field>
        <field name="model">forecast.pnl.line</field>
        <field name="arch" type="xml">
            <pivot>
                <field name="config_id" type="row"/>
                <field name="period_label" type="col"/>
                <field name="revenue" type="measure"/>
                <field name="actual_revenue" type="measure"/>
                <field name="variance_revenue" type="measure"/>
                <field name="ebitda" type="measure"/>
                <field name="actual_ebitda" type="measure"/>
            </pivot>
        </field>
    </record>

    <record id="action_forecast_pnl" model="ir.actions.act_window">
        <field name="name">P&amp;L Summary</field>
        <field name="res_model">forecast.pnl.line</field>
        <field name="view_mode">pivot,list,form</field>
    </record>
```

- [ ] **Step 4: Update menus in `forecast_financial_views.xml`**

Find the existing menu definitions and update/add:

Replace the existing `action_forecast_cashflow` action and all menu items:
```xml
    <record id="action_forecast_cashflow" model="ir.actions.act_window">
        <field name="name">Cashflow</field>
        <field name="res_model">forecast.cashflow.line</field>
        <field name="view_mode">list,form</field>
    </record>

    <!-- ── Menus ──────────────────────────────────────── -->

    <menuitem id="menu_forecast_financial"
              name="Analysis"
              parent="mml_forecast_core.menu_mml_forecasting_root"
              sequence="20"/>

    <menuitem id="menu_forecast_pnl"
              name="P&amp;L Summary"
              parent="menu_forecast_financial"
              action="action_forecast_pnl"
              sequence="10"/>

    <menuitem id="menu_forecast_cashflow"
              name="Cashflow"
              parent="menu_forecast_financial"
              action="action_forecast_cashflow"
              sequence="20"/>

    <menuitem id="menu_forecast_balance_sheet"
              name="Balance Sheet"
              parent="menu_forecast_financial"
              action="mml_forecast_financial.action_forecast_balance_sheet"
              sequence="30"/>

    <menuitem id="menu_forecast_variance"
              name="Variance"
              parent="menu_forecast_financial"
              action="mml_forecast_financial.action_forecast_variance"
              sequence="40"/>
```

- [ ] **Step 5: Commit**

```bash
git add mml_forecast_financial/views/forecast_balance_sheet_views.xml \
        mml_forecast_financial/views/forecast_variance_views.xml \
        mml_forecast_financial/views/forecast_financial_views.xml
git commit -m "feat: add standalone Balance Sheet and Variance views with Analysis menu + P&L pivot"
```

---

### Task 11: Security CSV + manifest finalization

**Files:**
- Modify: `mml_forecast_financial/security/ir.model.access.csv`
- Modify: `mml_forecast_financial/__manifest__.py`

- [ ] **Step 1: Add 3 new ACL rows to `ir.model.access.csv`**

Append to `mml_forecast_financial/security/ir.model.access.csv`:
```csv
access_forecast_opening_balance_user,forecast.opening.balance user,model_forecast_opening_balance,base.group_user,1,0,0,0
access_forecast_opening_balance_manager,forecast.opening.balance manager,model_forecast_opening_balance,base.group_system,1,1,1,1
access_forecast_balance_sheet_line_user,forecast.balance.sheet.line user,model_forecast_balance_sheet_line,base.group_user,1,0,0,0
access_forecast_balance_sheet_line_manager,forecast.balance.sheet.line manager,model_forecast_balance_sheet_line,base.group_system,1,1,1,1
access_forecast_variance_line_user,forecast.variance.line user,model_forecast_variance_line,base.group_user,1,0,0,0
access_forecast_variance_line_manager,forecast.variance.line manager,model_forecast_variance_line,base.group_system,1,1,1,1
```

- [ ] **Step 2: Update `mml_forecast_financial/__manifest__.py`**

Replace the existing `'data': [...]` block:
```python
    'data': [
        'security/ir.model.access.csv',
        'views/forecast_balance_sheet_views.xml',
        'views/forecast_variance_views.xml',
        'views/forecast_financial_views.xml',
    ],
```

- [ ] **Step 3: Run all pure-Python tests one final time**

```bash
cd /e/ClaudeCode/projects/mml.odoo/mml.odoo.apps/mml.forecasting
pytest mml_forecast_financial/tests/ -m "not odoo_integration" -q
```
Expected: all passed, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add mml_forecast_financial/security/ir.model.access.csv \
        mml_forecast_financial/__manifest__.py
git commit -m "feat: add ACL entries for new models and update manifest data[] order"
```

- [ ] **Step 5: Final push to remote**

```bash
git push origin main
```

---

## Chunk 5: HIAV Deploy + Smoke Test

### Task 12: Deploy to HIAV and smoke test

- [ ] **Step 1: SSH to HIAV and pull latest**

```bash
ssh root@100.94.135.90
cd /home/deploy/odoo-dev/addons/mml.forecasting
git pull
```
Expected: `Fast-forward` with new files listed.

- [ ] **Step 2: Upgrade modules**

```bash
cd /home/deploy/odoo-dev
docker compose run --rm odoo odoo -d mml_dev \
    -u mml_forecast_core,mml_forecast_financial --stop-after-init
```
Expected: `modules updated` with no `ERROR` lines. Check for warnings about missing external IDs.

- [ ] **Step 3: Restart Odoo**

```bash
docker compose restart odoo
```

- [ ] **Step 4: Smoke test — open browser at http://100.94.135.90:8090**

Work through the smoke test checklist from the spec:

1. [ ] Open All Forecasts → FY26 Base config → confirm it loads without error
2. [ ] Click **Pull from Accounting** → verify Opening Balance tab shows non-zero values for cash/receivables
3. [ ] Confirm manual override toggle on one field works (set `override_cash = True`, enter a value, confirm `effective_cash` shows the manual value in readonly)
4. [ ] Click **Reset to Draft** (if config was generated) → confirm P&L/Cashflow/BS/Variance tabs are empty
5. [ ] Click **Generate Forecast** → confirm all tabs populate: P&L, Cash Flow, Balance Sheet, Variance
6. [ ] On Cash Flow tab: verify `payments_fob_deposit` and `payments_fob_balance` columns visible (toggle optional columns on)
7. [ ] On Balance Sheet tab: verify `bs_difference` field visible; verify it does not show red decoration for most months (sanity check)
8. [ ] Click **Compute Variance** → confirm variance lines appear for any past periods; confirm P&L actual columns populate
9. [ ] Open any product (Inventory → Products) → verify **Forecasting** tab visible with `x_cbm_per_unit` field
10. [ ] Navigate to Analysis → Balance Sheet menu → confirm list view loads
11. [ ] Navigate to Analysis → Variance menu → confirm pivot view loads
12. [ ] Navigate to Analysis → P&L Summary → confirm actual/variance columns visible (optional columns)

- [ ] **Step 5: Populate product fields for key SKUs (optional but recommended)**

Set `x_cbm_per_unit` and `x_3pl_pick_rate` on 5–10 key SKUs via the product Forecasting tab, then regenerate the FY26 Base forecast and verify freight and 3PL lines are now non-zero in the COGS Detail tab.

---

## Post-Deploy Notes

**Existing generated configs (e.g. FY26 Base):** After upgrade, existing cashflow lines will have `payments_fob_deposit = 0` and `payments_fob_balance = 0` (the old `payments_fob` stored value is not migrated). `payments_fob` (the computed sum) will correctly show 0. Reset each config to Draft and re-generate to backfill all forecast data.

**Opening balance persistence:** `opening_balance_ids` are NOT cleared on Reset to Draft. Values pulled from accounting and any manual overrides persist across regenerations — this is intentional.

**Known limitations (Phase 2 backlog):**
- `bs_difference` is expected to be non-zero — missing fixed assets, GST credits, prepayments
- `trade_receivables` is at forecast grain (product/month), not invoice grain
- Per-supplier timing uses `seller_ids[0]` — multi-supplier products use primary supplier only
- No seasonality curves — flat monthly revenue from historical average
