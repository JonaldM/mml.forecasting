# Castaway Parity Sprint — Design Spec

**Date:** 2026-03-16
**Repo:** `mml.forecasting` (`https://github.com/JonaldM/mml.forecasting`)
**Modules affected:** `mml_forecast_core`, `mml_forecast_financial`
**Approach:** Expand `mml_forecast_financial` (Approach A) — no new modules

---

## Objective

Bring `mml_forecast_financial` to feature parity with Castaway Forecasting on three critical
dimensions, plus two data-quality fixes that are blocking cashflow accuracy:

1. **Balance Sheet** — add the third leg so the suite is a true 3-way integrated model
2. **UI Views** — build Odoo form/pivot/graph views so the finance team can use the module
3. **Variance Reporting** — pull actuals and produce full drill-down forecast vs. actual comparison
4. **Per-supplier cashflow timing** — fix wizard to match each COGS line to its product's supplier term
5. **Product field population** — add `x_cbm_per_unit` and `x_3pl_pick_rate` to `product.template`

---

## Benchmark Context

Castaway Forecasting's core value proposition is 3-way integrated forecasting (P&L + Balance Sheet
+ Cashflow) for SMEs, with variance reporting and scenario planning. After Sprints 1–2:

| Feature | Status |
|---------|--------|
| P&L (revenue, COGS waterfall, OpEx, EBITDA) | Done |
| Cashflow with supplier payment timing | Done (per-supplier timing broken — uses first term for all) |
| Scenario engine (volume %, FX, freight overrides) | Done |
| Multi-currency FX per config | Done |
| Balance Sheet | Missing — critical gap |
| Usable Odoo views | Missing — module not operable by finance team |
| Variance reporting | Missing |
| Product fields (CBM, 3PL rate) | Missing — freight/3PL lines show $0 |

Where MML already exceeds Castaway: import supply chain cashflow timing (deposit/balance split by
transit days + port of origin), COGS waterfall (FOB + FX + freight + duty + 3PL), demand-driven
from ROQ or sale history, native Odoo ERP integration.

---

## Deployment Workflow

Local dev → git push → HIAV server pull → module upgrade → smoke test.

```
1. Develop + test locally (pure-Python tests via pytest)
2. git push to mml.forecasting remote (github.com/JonaldM/mml.forecasting)
3. On HIAV (root@100.94.135.90):
   cd /home/deploy/odoo-dev/addons/mml.forecasting && git pull
4. docker compose run --rm odoo odoo -d mml_dev \
       -u mml_forecast_core,mml_forecast_financial --stop-after-init
5. docker compose restart odoo
6. Smoke test at http://100.94.135.90:8090
```

> **Post-upgrade note:** Existing `generated` forecast configs on HIAV will have stale or
> zeroed cashflow data (due to `payments_fob` converting from a stored input field to a computed
> sum field — existing rows will recompute to 0.0 until regenerated) and will be missing BS and
> variance data. Reset each config to Draft, then re-generate to backfill all forecast data.

---

## Section 1 — Data Models

### 1.1 `mml_forecast_core` — `product.template` extension

New file: `models/product_template_ext.py`

Two fields on `product.template`:

| Field | Type | Description |
|-------|------|-------------|
| `x_cbm_per_unit` | Float | Cubic metres per unit — drives freight cost calculation |
| `x_3pl_pick_rate` | Float (NZD) | Mainfreight pick/pack rate per unit |

These live in `mml_forecast_core` (not financial) because they are shared infrastructure —
`mml_forecast_demand` will also need them when the ROQ migration occurs in Sprint 3.

New file: `views/product_template_ext_views.xml` — adds a **Forecasting** page on the
`product.template` form view containing a single group with both fields.

No new security entries needed — fields inherit `product.template` ACL.

### 1.2 `forecast.opening.balance`

New model in `mml_forecast_financial`. Stores the opening BS position at `config.date_start`,
auto-pulled from Odoo's `account.move.line` trial balance with per-field manual override.

**One2one implementation pattern (Odoo has no `fields.One2one`):**
- `forecast.opening.balance` holds `config_id = fields.Many2one('forecast.config', required=True, ondelete='cascade')`
- `_sql_constraints = [('config_unique', 'UNIQUE(config_id)', 'Only one opening balance per forecast config.')]`
- `forecast.config` (via `forecast_config_ext.py`) holds `opening_balance_idss = fields.One2many('forecast.opening.balance', 'config_id')` — returns at most one record due to the unique constraint
  (Named `_ids` not `_id` per Odoo One2many convention, even though only one record is ever present)

**Fields:**

Each of the five BS opening positions has three fields:
- `opening_<item>` (Float) — auto-pulled value (written by `_pull_from_accounting`)
- `opening_<item>_manual` (Float) — user-entered override
- `override_<item>` (Boolean, default False) — if True, use manual value; auto value is still stored

One convenience computed field per item (not stored, used in BS generation):
- `effective_<item>` = `opening_<item>_manual if override_<item> else opening_<item>`
  Implement as `@api.depends` computed (not `store=True`) to keep it reactive.

| Item | Odoo `account_type` sources |
|------|---------------------------|
| `cash` | `asset_cash`, `asset_bank` |
| `receivables` | `asset_receivable` |
| `inventory` | `asset_current`, `asset_valuation` |
| `payables` | `liability_payable` |
| `equity` | `equity`, `equity_unaffected` + cumulative income/expense residual |

**Method:** `_pull_from_accounting(date_start)` — queries `account.move.line` where
`date < date_start` and `company_id = self.config_id.company_id.id`, groups by
`account_id.account_type`, sums `debit - credit` per type, maps to `opening_<item>` fields.
Re-pulling never overwrites `opening_<item>` where `override_<item>` is True.

### 1.3 `forecast.balance.sheet.line`

New model in `mml_forecast_financial`. One record per month per config.

**Fields:**

| Group | Field | Type | Derivation |
|-------|-------|------|------------|
| Assets | `cash` | Float | `effective_cash + cumulative_cashflow[M]` |
| | `trade_receivables` | Float | Σ revenue lines where `period_start ≤ M` and `receipt_month > M` |
| | `inventory_value` | Float | `inventory[M-1] + fob_balance_received[M] − total_cogs[M]` (rolled forward) |
| | `total_current_assets` | Float | Computed sum |
| Liabilities | `trade_payables` | Float | Σ `payments_fob_balance` from cashflow lines where `period_start > M` |
| | `total_current_liabilities` | Float | Computed sum |
| Equity | `retained_earnings` | Float | `effective_equity + cumulative_ebitda[M]` |
| | `total_equity` | Float | Computed |
| Check | `bs_difference` | Float | `total_assets − (total_liabilities + total_equity)` |

`total_current_assets`, `total_current_liabilities`, `total_equity`, `total_assets`, and
`bs_difference` are all `@api.depends` computed fields (not stored) on `forecast.balance.sheet.line`,
derived from the five base stored fields written by the wizard (`cash`, `trade_receivables`,
`inventory_value`, `trade_payables`, `retained_earnings`). The wizard writes only the base fields.

`bs_difference` is a health indicator only — not an enforced constraint. In a simplified model
it will not be exactly zero (missing: fixed assets, GST input tax credits, prepayments, accruals).
It is displayed in the BS view, highlighted red if `abs(bs_difference) > total_current_assets * 0.01`.

> **Note on trade_receivables accuracy:** Revenue lines are at forecast grain (one record per
> product/partner/month), not individual invoice grain. `trade_receivables` is therefore an
> approximation — directionally correct but will not match the Odoo AR ledger precisely.
> Listed in Known Limitations.

> **Dependency note for `_generate_balance_sheet_lines()`:** This method depends on
> `cumulative_cashflow` being populated on all cashflow lines before it is called. The existing
> wizard populates `cumulative_cashflow` in a post-creation loop before returning from
> `_generate_cashflow_lines()`, so the pipeline order (BS after cashflow, Section 2.5 step 7)
> satisfies this. Add an explicit ORM `flush()` call at the start of
> `_generate_balance_sheet_lines()` to ensure the DB is up to date:
> `self.env['forecast.cashflow.line'].flush_model()`.

### 1.4 `forecast.pnl.line` — actual and variance fields (additions)

Three new stored Float fields populated by `action_compute_variance()`:

`actual_revenue`, `actual_cogs`, `actual_opex`

Two new computed (not stored) fields derived from the above:

`actual_gross_margin` = `actual_revenue − actual_cogs`
`actual_ebitda` = `actual_gross_margin − actual_opex`

These are `@api.depends('actual_revenue', 'actual_cogs', 'actual_opex')` computed fields —
not stored, to avoid staleness if individual actuals are refreshed separately.

Three new computed variance fields:

`variance_revenue` = `actual_revenue − revenue`
`variance_revenue_pct` = `variance_revenue / revenue * 100` (guarded: returns 0.0 if `revenue == 0`)
`variance_ebitda_pct` = `(actual_ebitda − ebitda) / ebitda * 100` (guarded: returns 0.0 if `ebitda == 0`)

### 1.5 `forecast.variance.line`

New model in `mml_forecast_financial`. Product/partner/period grain for drill-down variance.

| Field | Type | Description |
|-------|------|-------------|
| `config_id` | Many2one `forecast.config` | Required, cascade delete |
| `period_start` | Date | Month start |
| `period_label` | Char | e.g. `2026-04` |
| `product_id` | Many2one `product.product` | |
| `partner_id` | Many2one `res.partner` | |
| `brand` | Char | Resolved at generation time |
| `category` | Char | From product category |
| `forecast_units` | Float | From `forecast.revenue.line` |
| `forecast_revenue` | Float | From `forecast.revenue.line` |
| `actual_units` | Float | From confirmed `sale.order.line` in period |
| `actual_revenue` | Float | From confirmed `sale.order.line` in period |
| `variance_units` | Float | Computed: `actual_units − forecast_units` |
| `variance_revenue` | Float | Computed: `actual_revenue − forecast_revenue` |
| `variance_revenue_pct` | Float | Computed: `variance_revenue / forecast_revenue * 100` (returns 0.0 if `forecast_revenue == 0`) |

### 1.6 Minor model changes to existing models

**`forecast.cashflow.line`:** Split `payments_fob` into two stored Float fields:
- `payments_fob_deposit` — deposit payments
- `payments_fob_balance` — balance payments (goods received; used for BS inventory calculation)

Convert existing `payments_fob` to a **computed field** (not stored input):
```python
@api.depends('payments_fob_deposit', 'payments_fob_balance')
def _compute_payments_fob(self):
    for rec in self:
        rec.payments_fob = rec.payments_fob_deposit + rec.payments_fob_balance
```

**Update `_compute_cashflow` `@api.depends`:** Replace `'payments_fob'` with
`'payments_fob_deposit', 'payments_fob_balance'` so `total_outflows` and `net_cashflow`
recompute correctly when the split fields change.

`payments_fob` should be `store=True` on the computed field for search/filter performance.

**`forecast.revenue.line`:** Add `receipt_month` (Date, stored) — first day of the month
in which the customer receipt lands. Populated during `_generate_revenue_lines()` — computed
once from `CustomerTerm.get_default_receipt_date()` and stored, eliminating the duplicate call
currently made in `_generate_cashflow_lines()`.

**`forecast.cogs.line`:** Add `supplier_id` (Many2one `res.partner`, optional) — populated
during `_generate_cogs_lines()`. Requires extending `_get_supplier_info()` to also return
`partner_id` (the `res.partner.id` of `seller_ids[0]`).

**`forecast.config` (via `forecast_config_ext.py`):** Add the following One2many fields:
- `opening_balance_ids = fields.One2many('forecast.opening.balance', 'config_id')` — at most 1 record
- `balance_sheet_line_ids = fields.One2many('forecast.balance.sheet.line', 'config_id')`
- `variance_line_ids = fields.One2many('forecast.variance.line', 'config_id')`

---

## Section 2 — Computation Logic

### 2.1 Per-supplier cashflow timing fix

**File:** `wizards/forecast_generate_wizard.py`, method `_generate_cashflow_lines()`

Current bug: uses `supplier_terms[0]` for every product, ignoring actual supplier assignments.

> **Note on `forecast.supplier.term.transit_days`:** This is a Python `@property` (not an ORM
> field) computed from `origin_port_id.transit_days_nz`. Access via `term.transit_days` as today.

Fix:
1. Build `supplier_term_map = {term.supplier_id.id: term for term in config.supplier_term_ids}`
   at the start of the method.
2. For each `cogs_line`, look up `supplier_term_map.get(cogs.supplier_id.id)`.
3. If found: use that term's `deposit_pct`, `deposit_trigger_days`, `transit_days`.
4. If not found: fall back to config defaults (deposit 3 months back, balance 1 month back, 30%).

**Accumulator naming:** Align with existing code variable names in `forecast_generate_wizard.py`:
- Deposit accumulator: `fob_deposit_by_month` (existing name — keep it)
- Balance accumulator: `fob_balance_by_month` (existing name — keep it)

Emit deposit and balance **separately** into these accumulators (they are already separate
in the current code for the combined `fob_deposit_by_month` / `fob_balance_by_month` split).
Write to `payments_fob_deposit` and `payments_fob_balance` respectively on the cashflow line
records (replacing the current single `payments_fob` write).

### 2.2 Revenue line `receipt_month` population

**File:** `wizards/forecast_generate_wizard.py`, method `_generate_revenue_lines()`

After computing `sell_price`, also compute `receipt_date` via
`CustomerTerm.get_default_receipt_date(config, partner_id, period_start)` and store
`receipt_month = receipt_date.replace(day=1)` on the revenue line.

This computation already exists in `_generate_cashflow_lines()` — by moving it here and storing
it on the revenue line, the cashflow method can read `rev.receipt_month` instead of recomputing.

### 2.3 `_generate_balance_sheet_lines(config, months)`

New wizard method, called after `_generate_cashflow_lines()`.

```python
def _generate_balance_sheet_lines(self, config, months):
    self.env['forecast.cashflow.line'].flush_model()  # ensure cumulative_cashflow is committed

    ob = config.opening_balance_ids[:1]  # the single opening balance record (One2many, at most 1)
    if not ob:
        _logger.warning('No opening balance on config %s — BS lines will use zero opening values', config.id)

    inventory = ob.effective_inventory if ob else 0.0
    cumulative_ebitda = 0.0
    cashflow_by_month = {l.period_start: l for l in config.cashflow_line_ids}
    pnl_by_month = {l.period_start: l for l in config.pnl_line_ids}
    revenue_lines = config.revenue_line_ids  # full set, filtered per period below
    # O(n²) for simplicity — acceptable at 12–24 month horizons.
    # For longer horizons, replace with a suffix-sum pass (iterate once in reverse, accumulate).
    future_fob_balance = {
        m[0]: sum(
            l.payments_fob_balance for l in config.cashflow_line_ids
            if l.period_start > m[0]
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
            if r.period_start <= period_start and r.receipt_month and r.receipt_month > period_start
        )
        fob_received = cf.payments_fob_balance if cf else 0.0
        total_cogs = pnl.total_cogs if pnl else 0.0
        inventory += fob_received - total_cogs
        trade_payables = future_fob_balance.get(period_start, 0.0)
        cumulative_ebitda += (pnl.ebitda if pnl else 0.0)
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

    self.env['forecast.balance.sheet.line'].create(lines_data)
```

### 2.4 `_compute_variance_lines(config, past_months)` — shared internal method

Extract as a private method called both by `generate()` (step 8) and
`action_compute_variance()`. This avoids duplicating the two-pass logic.

**Pass 1 — Product-level variance (`forecast.variance.line`):**

Only processes periods where `period_start < date.today()`.

```python
for period_start, period_label in past_months:
    period_end = period_start + relativedelta(months=1)
    actual_lines = SaleOrderLine.search([
        ('order_id.state', 'in', ['sale', 'done']),
        ('order_id.date_order', '>=', period_start),
        ('order_id.date_order', '<', period_end),
    ])
    # group by (product_id, partner_id) → actual_units, actual_revenue
    # match against forecast.revenue.line for same config/period
    # upsert forecast.variance.line (search existing, write or create)
```

**Pass 2 — P&L summary actuals (`forecast.pnl.line` `actual_*` fields):**

```python
for pnl_line in config.pnl_line_ids.filtered(lambda l: l.period_start < date.today()):
    period_end = pnl_line.period_start + relativedelta(months=1)
    aml = AccountMoveLine.search([
        ('move_id.state', '=', 'posted'),
        ('date', '>=', pnl_line.period_start),
        ('date', '<', period_end),
        ('company_id', '=', config.company_id.id),
    ])
    pnl_line.write({
        'actual_revenue': sum(
            l.balance for l in aml
            if l.account_id.account_type in ('income', 'income_other')
        ),
        'actual_cogs': sum(
            l.balance for l in aml
            if l.account_id.account_type == 'expense_direct_cost'
        ),
        'actual_opex': sum(
            l.balance for l in aml
            if l.account_id.account_type == 'expense'
        ),
    })
    # actual_gross_margin and actual_ebitda are computed fields — no write needed
```

Note: `line.write({...})` batches all three fields into one SQL UPDATE per P&L line.

### 2.5 Updated generation pipeline

**`generate(config)` preamble — unlinks (add to existing unlink block):**
```python
config.revenue_line_ids.unlink()
config.cogs_line_ids.unlink()
config.pnl_line_ids.unlink()
config.cashflow_line_ids.unlink()
config.balance_sheet_line_ids.unlink()   # new
config.variance_line_ids.unlink()        # new
```

**Step order:**
```
1. _build_month_buckets()
2. _get_demand_forecast()           — unchanged
3. _generate_revenue_lines()        — now also stores receipt_month
4. _generate_cogs_lines()           — now also stores supplier_id
5. _generate_pnl_lines()            — unchanged
6. _generate_cashflow_lines()       — per-supplier timing; writes fob_deposit + fob_balance separately
7. _generate_balance_sheet_lines()  — new; reads cumulative_cashflow after flush
8. _compute_variance_lines()        — new shared method; skips if all periods are in the future
```

---

## Section 3 — Views & UX

### 3.1 `forecast.config` form — updated tab structure

Header buttons (state-dependent visibility):
- **Pull from Accounting** — always available while not locked; creates/updates opening balance
- **Generate Forecast** — available in `draft` state
- **Compute Variance** — available in `generated` state; `invisible` if no past periods exist
- **Lock** — available in `generated` state
- **Reset to Draft** — available in `generated` and `locked` states

`action_compute_variance()` is defined on `forecast.config` (in `forecast_config_ext.py`) and
calls `self.env['forecast.generate.wizard']._compute_variance_lines(self, past_months)` directly.
No separate wizard dialog is needed — this is consistent with how `action_generate_forecast()`
delegates to `forecast.generate.wizard.generate(self)`.

**Ten tabs:**

| Tab | Content | Editable |
|-----|---------|----------|
| Setup | name, date_start, horizon_months, freight_rate_cbm, volume_adjustment_pct, tax_id, company_id | Draft only |
| FX Rates | Inline `forecast.fx.rate` list | Draft only |
| Supplier Terms | Inline `forecast.supplier.term` list | Draft only |
| Customer Terms | Inline `forecast.customer.term` list | Draft only |
| OpEx | Inline `forecast.opex.line` list | Draft only |
| Opening Balance | `forecast.opening.balance` fields — per row: auto value (read-only), override toggle, manual value | Always (not locked) |
| P&L Summary | Read-only `forecast.pnl.line` tree with forecast + actual + variance columns | Read-only |
| Cash Flow | Read-only `forecast.cashflow.line` tree with `payments_fob_deposit` + `payments_fob_balance` columns | Read-only |
| Balance Sheet | Read-only `forecast.balance.sheet.line` tree; `bs_difference` decorated red if > 1% of assets | Read-only |
| Variance | Read-only `forecast.variance.line` tree (summary) | Read-only |

### 3.2 Standalone analysis views

All filterable by `config_id`.

| View | Type | Axes / Values |
|------|------|---------------|
| P&L Summary | Pivot + bar graph | Rows: period_label; Columns: metric; Values: forecast vs actual |
| Cash Flow | List + line graph | X: period; Y: net_cashflow + cumulative overlay |
| Balance Sheet | List | Rows: period; cash / receivables / inventory / payables / equity / bs_difference |
| Revenue Detail | Pivot | Rows: brand; Columns: period; Values: revenue (drillable to product) |
| COGS Detail | Pivot | Rows: brand/category; Columns: period; Values: fob/freight/duty/3pl |
| Variance | Pivot | Rows: product/partner; Columns: period; Values: variance_revenue_pct |

Variance pivot conditional formatting (positive = beat forecast = good):
```xml
decoration-success="variance_revenue_pct > 0"
decoration-danger="variance_revenue_pct &lt; -10"
```

### 3.3 Product template extension view

New **Forecasting** page on `product.template` form (via `inherit` in `mml_forecast_core`):

```xml
<page string="Forecasting">
    <group>
        <field name="x_cbm_per_unit"/>
        <field name="x_3pl_pick_rate"/>
    </group>
</page>
```

### 3.4 Menu structure

```
Forecasting  (top-level, mml_forecast_core)
├── All Forecasts
├── Analysis
│   ├── P&L Summary
│   ├── Cash Flow
│   ├── Balance Sheet       ← new
│   ├── Revenue Detail
│   ├── COGS Detail
│   └── Variance            ← new
└── Configuration
    └── Origin Ports
```

---

## Section 4 — Module File Structure

### `mml_forecast_core/` changes

```
models/
  __init__.py                       MODIFIED — add product_template_ext import
  product_template_ext.py           NEW
views/
  product_template_ext_views.xml    NEW
```

No new security entries (fields inherit `product.template` ACL).

### `mml_forecast_financial/` changes

```
models/
  __init__.py                       MODIFIED — add 3 new model imports
  forecast_config_ext.py            MODIFIED — add opening_balance_ids, balance_sheet_line_ids,
                                               variance_line_ids One2many fields;
                                               add action_compute_variance(),
                                               action_pull_opening_balance()
  forecast_revenue_line.py          MODIFIED — add receipt_month field
  forecast_cogs_line.py             MODIFIED — add supplier_id field
  forecast_cashflow_line.py         MODIFIED — add payments_fob_deposit, payments_fob_balance;
                                               convert payments_fob to computed sum;
                                               update _compute_cashflow @api.depends
  forecast_pnl_line.py              MODIFIED — add actual_revenue, actual_cogs, actual_opex (stored);
                                               add actual_gross_margin, actual_ebitda (computed);
                                               add variance_revenue, variance_revenue_pct,
                                               variance_ebitda_pct (computed)
  forecast_opening_balance.py       NEW
  forecast_balance_sheet_line.py    NEW
  forecast_variance_line.py         NEW

wizards/
  __init__.py                       MODIFIED — no new wizard class; _compute_variance_lines
                                               added as method on ForecastGenerateWizard
  forecast_generate_wizard.py       MODIFIED — per-supplier timing; receipt_month; supplier_id;
                                               split fob deposit/balance; add
                                               _generate_balance_sheet_lines();
                                               add _compute_variance_lines()

views/
  forecast_config_views.xml         MODIFIED — Opening Balance tab, BS tab, Variance tab,
                                               new buttons (Pull from Accounting, Compute Variance)
  forecast_pnl_views.xml            MODIFIED — actual_* + variance_* columns
  forecast_cashflow_views.xml       MODIFIED — payments_fob_deposit + payments_fob_balance columns
  forecast_balance_sheet_views.xml  NEW
  forecast_variance_views.xml       NEW
  forecast_analysis_views.xml       MODIFIED — add BS + Variance menu items

security/
  ir.model.access.csv               MODIFIED — 3 new rows:
                                               forecast.opening.balance,
                                               forecast.balance.sheet.line,
                                               forecast.variance.line
                                               (all user/manager tiers, consistent with existing rows)

__manifest__.py                     MODIFIED — add to data[]:
                                               'models/forecast_opening_balance.py' (via __init__),
                                               new view XML files in dependency order:
                                               security CSV first, then views
```

**`__init__.py` update (models):**
```python
from . import forecast_opening_balance
from . import forecast_balance_sheet_line
from . import forecast_variance_line
```

**`__manifest__.py` data[] additions (order matters — security before views):**
```python
'security/ir.model.access.csv',          # already present — keep first
'views/forecast_balance_sheet_views.xml',
'views/forecast_variance_views.xml',
'views/forecast_analysis_views.xml',     # already present — update in place
'views/product_template_ext_views.xml',  # in mml_forecast_core manifest
```

**Total:** 5 new Python files, 3 new XML files, 10 modified files. No new modules.

---

## Known Limitations and Phase 2 Backlog

| Item | Notes |
|------|-------|
| `bs_difference` non-zero | Expected — missing fixed assets, GST input tax credits, prepayments, accruals |
| Trade receivables approximation | Forecast grain (month/product), not invoice grain — will not match AR ledger precisely |
| Flat monthly revenue | No seasonality curves — Phase 2 backlog per sprint brief |
| Per-supplier timing uses primary seller | `cogs.supplier_id` from `seller_ids[0]` — multi-supplier products use primary supplier only |
| GST refund inflow | Not modelled — Phase 2 backlog |
| Storage costs | Pallet storage not in 3PL rate — Phase 2 backlog |
| BS horizon boundary | `trade_payables` = $0 in final month (no future commitments visible beyond horizon) |
| Actuals account mapping | Uses Odoo standard `account_type` — non-standard chart of accounts may need manual remapping |

---

## Testing Strategy

**Pure-Python (no Odoo required):**
- `test_bs_computation.py` — BS roll-forward with synthetic cashflow/P&L data; assert `cash`, `inventory`, `retained_earnings` for known inputs
- `test_per_supplier_timing.py` — assert deposit/balance months for two suppliers with different lead times on the same config
- `test_variance_calculation.py` — variance % computation including zero-division guards
- `test_effective_opening_balance.py` — assert `effective_<item>` returns manual value when override is True, auto value otherwise

**Odoo integration (`TransactionCase`):**
- `test_bs_integration.py` — generate forecast, assert BS line count = horizon_months, `bs_difference` within 10% of assets (loose tolerance for test data)
- `test_variance_integration.py` — create confirmed SO lines, call `action_compute_variance()`, assert `actual_units` and `actual_revenue` populated on variance lines
- `test_opening_balance_pull.py` — post journal entries to asset_cash and liability_payable accounts, call `_pull_from_accounting()`, assert field values; then set override=True, re-pull, assert manual value preserved
- `test_payments_fob_split.py` — generate cashflow lines, assert `payments_fob == payments_fob_deposit + payments_fob_balance` for all lines; assert `total_outflows` computed correctly

**Smoke test checklist on HIAV after deploy:**
1. Open All Forecasts → FY26 Base config → confirm it loads
2. Click Pull from Accounting → verify opening balance fields populated (non-zero cash/receivables)
3. Reset to Draft → Generate Forecast → confirm P&L, Cashflow, Balance Sheet, Variance tabs all populated
4. On Balance Sheet tab: verify `bs_difference` field visible; check it is less than 50% of `total_current_assets` (sanity, not correctness)
5. Click Compute Variance → confirm variance lines appear for past periods
6. Open any product → verify Forecasting tab visible with `x_cbm_per_unit` field
7. Analysis → Balance Sheet menu item → pivot/list loads without error
8. Analysis → Variance menu item → pivot loads without error
9. Confirm `payments_fob_deposit` and `payments_fob_balance` appear as separate columns on Cash Flow tab
