# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Read the parent repo's `CLAUDE.md` at `E:\ClaudeCode\projects\mml.odoo.apps\CLAUDE.md` for company context, platform conventions, and cross-module integration patterns. This file covers only the `mml.forecasting` sub-repo.

---

## Repo Purpose

A standalone forecasting suite for Odoo 19, structured as two independently installable apps. The repo lives at `https://github.com/JonaldM/mml.forecasting`.

**Source for the planned `mml_forecast_demand` module (not yet migrated):** `E:\ClaudeCode\projects\mml.odoo.apps\roq.model\mml_roq_forecast\`

---

## Module Structure

```
mml.forecasting/
├── mml_forecast_core/       # application=True — Shared infrastructure + top-level app menu
└── mml_forecast_financial/  # application=False — P&L, cashflow, scenario engine
```

`mml_forecast_demand` (ROQ demand planning migration from `mml_roq_forecast`) is planned but not yet created in this repo. When built, it will depend on `mml_forecast_core` only.

### Module Dependency Chain

```
mml_base ←── mml_forecast_core ←── mml_forecast_financial
                                ←── mml_forecast_demand  (future)
```

Modules do NOT import each other directly. `mml_forecast_financial` detects `mml_forecast_demand` at runtime via `self.env.get('roq.forecast.run')`.

---

## Key Models

### mml_forecast_core

| Model | Description |
|-------|-------------|
| `forecast.config` | Central record: period, scenario, FX rates, import tax, state machine (`draft → generated → locked`). Owns all `One2many` child lines. |
| `forecast.fx.rate` | Per-config FX table. Convention: `rate_to_nzd` = "NZD buys X FCY" (e.g. USD=0.60 means 1 NZD = 0.60 USD). `nzd_per_unit` auto-inverts for COGS. |
| `forecast.origin.port` | Port registry with `transit_days_nz`. Keyed by 5-char UN/LOCODE (always uppercased). |
| `forecast.supplier.term` | Per-supplier deposit %, lead times, origin port. `transit_days` and `total_lead_days` are Python `@property` (not ORM fields). |
| `forecast.customer.term` | Per-customer payment rules. Three rule types: `days_then_dom`, `next_month_dom`, `end_of_following`. Core method: `compute_receipt_date(invoice_date) → date`. Class method: `get_default_receipt_date(config, partner_id, invoice_date)` with 45-day/20th fallback. |

### mml_forecast_financial

| Model | Description |
|-------|-------------|
| `forecast.revenue.line` | Units × sell price per product/customer/month. |
| `forecast.cogs.line` | Full landed cost waterfall: FOB (FCY→NZD via FX) + freight (CBM × rate) + duty (% of FOB NZD) + 3PL pick rate. |
| `forecast.pnl.line` | Monthly P&L aggregate from revenue + COGS + OpEx. |
| `forecast.cashflow.line` | Monthly cash flow with supplier payment timing (deposit/balance bucketed to preceding months) and customer receipt timing (shifted by payment terms). |
| `forecast.opex.line` | Fixed (NZD/month) or variable (% of revenue) operating expenses. |
| `forecast.generate.wizard` | `TransientModel` — entire generation pipeline in one class. Called via `forecast.config.action_generate_forecast()`. |

---

## Generation Pipeline

`forecast.generate.wizard.generate(config)` runs these steps in order:

1. **Month buckets** — list of `(date, label)` tuples for the horizon
2. **Demand** — tries `roq.forecast.run` (if installed), falls back to trailing 12-month `sale.order.line` history
3. **Revenue lines** — demand × sell price (pricelist → list_price fallback)
4. **COGS lines** — demand × full waterfall (FOB from `product.seller_ids`, FX from config, CBM/tariff/3PL from custom product fields)
5. **P&L lines** — monthly aggregate of revenue + COGS + OpEx
6. **Cashflow lines** — supplier timing (deposit/balance/freight/duty bucketed to preceding months) + customer receipt timing

Cashflow timing logic: `ceil(deposit_trigger_days / 30)` months back for deposit; `ceil(transit_days_nz / 30)` months back for balance+freight; duty in the sale month. Revenue inflows shifted by `forecast.customer.term.compute_receipt_date()`.

---

## Product Custom Fields Required

The COGS wizard uses `getattr()` to safely access these fields — they produce zero if absent:

| Field | Technical Name | Type |
|-------|---------------|------|
| Brand | `x_brand` on `product.template` | Char/Selection |
| CBM per unit | `x_cbm_per_unit` on `product.template` | Float |
| Tariff rate % | `x_tariff_rate` on `product.template` | Float |
| 3PL pick rate | `x_3pl_pick_rate` on `product.template` | Float (NZD) |

---

## Running Tests

Pure-Python tests (when added) can run without Odoo from the workspace root:

```bash
pytest -m "not odoo_integration" -q
```

All current tests are Odoo integration tests (`TransactionCase`) and require a live Odoo database:

```bash
# Install/update modules
python odoo-bin -i mml_forecast_core,mml_forecast_financial -d <db> --stop-after-init

# Run all forecasting tests
python odoo-bin --test-enable -u mml_forecast_core,mml_forecast_financial -d <db> --stop-after-init

# Run a specific test class
python odoo-bin --test-enable -d <db> --test-tags /mml_forecast_financial:TestCashflowTiming
```

---

## Odoo 19 Conventions (this repo)

- `name_get()` is removed in Odoo 19 — use `_compute_display_name()` instead.
- View attributes use direct `invisible`/`readonly` (not `attrs=`).
- `self.env.get('model.name')` returns `None` if a module is not installed — used for optional dependency detection.
- `application = True` only on `mml_forecast_core`; `mml_forecast_financial` is `application = False`.
- Security: `ir.model.access.csv` + record rules per module. No hardcoded credentials.

---

## Planned Work (from `docs/plans/`)

The refactor plan at `docs/plans/2026-03-05-forecasting-suite-refactor.md` defines four sprints. Current state: Sprints 1–2 complete (core + financial scaffold). Remaining:

- **Sprint 3** — Migrate `mml_roq_forecast` → `mml_forecast_demand` (new module in this repo)
- **Sprint 4** — Wire ROQ demand into financial wizard; full cashflow rewrite with per-supplier timing

Key known gap: the cashflow wizard currently uses only `supplier_terms[0]` for timing — future work should match each COGS line to its product's actual supplier term.

Phase 2 backlog (not in current plan): import tax refund inflow (~2 month lag), pallet storage costs, seasonality curves, LC bank processing time.

## Available Commands

- `/plan` — implementation plan before Sprint 3 (demand migration) or Sprint 4 (cashflow rewrite)
- `/tdd` — write pure-Python tests for generation pipeline logic first
- `/code-review` — review wizard and model changes before release
- `/build-fix` — diagnose `odoo-bin --test-enable` test failures
