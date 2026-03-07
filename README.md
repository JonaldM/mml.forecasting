# MML Forecasting Suite

Odoo 19 financial and demand forecasting for **MML Consumer Products Ltd**. A standalone suite composed of two independently installable modules built on a shared core.

**Repo:** `https://github.com/JonaldM/mml.forecasting`

---

## Modules

| Module | `application` | Purpose |
|---|---|---|
| `mml_forecast_core` | Yes — "Forecasting" home screen tile | Shared config infrastructure: FX rates, origin ports, supplier terms, customer payment terms, scenario management |
| `mml_forecast_financial` | No | Full P&L and cashflow forecast driven by demand signals: revenue, COGS (full landed cost waterfall), operating expenses, cashflow with payment timing |

`mml_forecast_demand` — ROQ demand engine migration from `mml_roq_forecast` — is planned but not yet in this repo. When built, it will depend on `mml_forecast_core` only and slot into the generation pipeline automatically via `env.get('roq.forecast.run')`.

---

## Architecture

```
mml_base
    │
mml_forecast_core          ← application=True (home tile + menu)
    │
mml_forecast_financial     ← application=False (P&L, cashflow tabs)
    │
mml_forecast_demand        ← planned (ROQ demand migration)
```

Modules do not import each other directly. `mml_forecast_financial` detects `mml_forecast_demand` at runtime via `self.env.get('roq.forecast.run')` — if absent, it falls back to trailing 12-month `sale.order.line` history.

---

## mml_forecast_core

Shared infrastructure for the forecasting suite. Provides the central `forecast.config` record that all child modules attach to.

### Key models

| Model | Description |
|---|---|
| `forecast.config` | Central forecast record — scenario, horizon, status. Owns all `One2many` child lines. State machine: `draft → generated → locked`. |
| `forecast.fx.rate` | Per-config FX table. `rate_to_nzd` = "NZD buys X FCY" (e.g. USD=0.60 means 1 NZD = 0.60 USD). `nzd_per_unit` auto-inverts for COGS calculations. |
| `forecast.origin.port` | Port registry keyed by UN/LOCODE (5 chars, auto-uppercase). Holds `transit_days_nz` for cashflow timing. Default ports seeded: Shanghai, Ningbo, Shenzhen, Ho Chi Minh City, Auckland, Tauranga (20 total). |
| `forecast.supplier.term` | Per-supplier config: deposit %, production lead days, origin port. `transit_days` and `total_lead_days` are Python properties, not ORM fields. |
| `forecast.customer.term` | Per-customer payment rules. Three rule types: `days_then_dom`, `next_month_dom`, `end_of_following`. Core method: `compute_receipt_date(invoice_date) → date`. |

### Test status

2 pure-Python tests passing (no Odoo required). All other tests are Odoo integration tests.

```bash
cd mml.forecasting
pytest -m "not odoo_integration" -q
```

---

## mml_forecast_financial

Full financial forecast driven by demand signals.

### What it generates

A `forecast.config` record with a horizon (e.g. 12 months) generates:

- **Revenue lines** — units × sell price per product/customer/month
- **COGS lines** — full landed cost waterfall per product/month:
  - FOB cost (FCY → NZD via FX rate)
  - Sea freight (CBM × rate per CBM)
  - Import duty (% of FOB NZD from `x_tariff_rate` product field)
  - 3PL pick rate (NZD from `x_3pl_pick_rate` product field)
- **P&L lines** — monthly aggregate: revenue − COGS − OpEx
- **OpEx lines** — fixed (NZD/month) or variable (% of revenue) operating expenses
- **Cashflow lines** — monthly net cash with:
  - Supplier outflows bucketed by timing (deposit triggered by `deposit_trigger_days`, balance + freight at shipment, duty in sale month)
  - Customer inflows shifted by `forecast.customer.term.compute_receipt_date()`

### Generation pipeline

`forecast.generate.wizard.generate(config)` orchestrates the full pipeline:

1. Build month buckets for the horizon
2. Retrieve demand (`roq.forecast.run` if installed; else trailing 12M `sale.order.line` history)
3. Generate revenue lines
4. Generate COGS lines (full landed cost waterfall)
5. Aggregate P&L lines
6. Project cashflow with payment timing

### Required product fields

The COGS wizard reads these custom product fields via `getattr()` — they produce zero if absent:

| Field | Technical name | Notes |
|---|---|---|
| Brand | `x_brand` on `product.template` | Display grouping |
| CBM per unit | `x_cbm_per_unit` on `product.template` | Required for freight cost |
| Tariff rate % | `x_tariff_rate` on `product.template` | Import duty |
| 3PL pick rate | `x_3pl_pick_rate` on `product.template` | NZD per pick |

### Test status

29 Odoo integration tests (require `odoo-bin`). No pure-Python tests yet.

---

## Installation

```bash
# Platform layer first
odoo-bin -d <db> -i mml_base --stop-after-init

# Core (required first — provides the menu and shared models)
odoo-bin -d <db> -i mml_forecast_core --stop-after-init

# Financial module
odoo-bin -d <db> -i mml_forecast_financial --stop-after-init
```

---

## Running tests

```bash
# Pure-Python structural tests (no Odoo required — fast)
cd mml.forecasting
pytest -m "not odoo_integration" -q

# Odoo integration tests
odoo-bin --test-enable -u mml_forecast_core,mml_forecast_financial \
  -d <db> --stop-after-init
```

---

## Planned work

| Sprint | Scope | Status |
|---|---|---|
| Sprint 1 — Core scaffold | `forecast.config`, FX rates, origin ports, supplier/customer terms | Complete |
| Sprint 2 — Financial engine | Revenue, COGS waterfall, P&L, cashflow, OpEx | Complete |
| Sprint 3 — Demand migration | Migrate `mml_roq_forecast` → `mml_forecast_demand` in this repo | Planned |
| Sprint 4 — Full integration | Wire ROQ demand into financial wizard; per-supplier cashflow timing | Planned |

### Known gaps

- Cashflow wizard currently uses only `supplier_terms[0]` for timing — should match each COGS line to its product's actual supplier term (Sprint 4).
- Phase 2 backlog: import tax refund inflow (~2-month lag), pallet storage costs, seasonality curves, LC bank processing time.
