# Sprint Brief: MML Forecast Module — Architecture & Integration

## Objective

Consolidate the existing ROQ (demand forecasting) module and the new financial forecasting engine into a unified, SaaS-ready forecasting suite under a three-module architecture. The financial forecasting scaffold is provided in `/mml_financial_forecast/` and needs to be evaluated, refactored, and integrated natively into our Odoo 19 stack.

---

## Architecture: Three-Module Structure

```
mml_forecast_core/          # Shared infrastructure
mml_forecast_demand/        # ROQ demand planning (existing module, to be migrated)
mml_forecast_financial/     # P&L, cash flow, scenario engine (new, scaffold provided)
```

Each module is independently installable. Both `demand` and `financial` depend on `core`, but NOT on each other. A customer can install:

- `core` + `demand` only (inventory-focused distributor)
- `core` + `financial` only (service business, e.g. dentist forecasting appointment revenue)
- All three (MML's use case — full demand-driven financial forecasting)

### mml_forecast_core

Shared models and config that both pillars use:

- `forecast.config` — period definition, scenario tags, state machine (draft → generated → locked), import tax selection (`tax_id` → `account.tax`)
- `forecast.fx.rate` — FX rate table per config (editable in GUI)
- `forecast.origin.port` — origin port registry with transit days to NZ (shared with ROQ port-based consolidation)
- `forecast.supplier.term` — per-supplier deposit %, lead times, origin port linkage (editable in GUI)
- `forecast.customer.term` — per-customer payment rules with date-snapping logic (editable in GUI)
- `forecast.scenario` — scenario management, duplication, side-by-side comparison
- Period/month bucket utilities
- Base menu: **Forecasting** (top-level app)

### mml_forecast_demand

Migrated from the existing ROQ module. This is the demand engine.

- All existing ROQ models (reorder quantity, demand signals, safety stock, lead times)
- Exposes a standard demand interface to downstream consumers:

```python
# The contract: any demand source must produce this structure
[
    {
        'product_id': int,
        'partner_id': int,        # optional — demand may not be customer-specific
        'period_start': date,
        'period_label': str,      # e.g. '2026-04'
        'forecast_units': float,
        'brand': str,
        'category': str,
    },
]
```

- Menu: **Forecasting → Demand Planning**
- If `mml_forecast_financial` is not installed, this operates standalone

### mml_forecast_financial

New module. Scaffold provided in `/mml_financial_forecast/`.

- Revenue forecasting (units × sell price × channel)
- COGS waterfall (FOB + freight + duty + 3PL)
- OpEx layer (fixed monthly + variable % of revenue)
- P&L summary (monthly, 12-month rolling)
- Cash flow timing (customer payment term rules → receivables; payable timing → outflows)
- Scenario engine (base / optimistic / pessimistic / custom with driver overrides)
- Menu: **Forecasting → Financial Planning**

**Demand source logic:**
1. If `mml_forecast_demand` is installed → pull from ROQ forecast lines
2. If NOT installed → fall back to trailing 12-month sale order history as proxy
3. Future: manual entry / CSV upload adapter for service businesses

---

## Key Design Decisions

### Customer Payment Terms (Hardcoded Config Table)

Payment term rules are stored per-customer in `forecast.customer.term`, editable in the GUI. NOT extending Odoo's native `account.payment.term` — our rules are quirky and we have a small, stable set of retail customers.

| Customer | Rule Type | Parameters |
|---|---|---|
| Default | `days_then_dom` | 45 days buffer, snap to 20th |
| Harvey Norman | `next_month_dom` | 15th of following month |
| Briscoes | `end_of_following` | Last calendar day of following month |

The `compute_receipt_date(invoice_date)` method on `forecast.customer.term` handles all date-snapping logic. Review the implementation in the scaffold for edge cases (month boundaries, leap years).

### FX Rate Convention

Stored as "NZD buys X foreign" — matches how Jono thinks about rates:

| Currency | Rate | Meaning |
|---|---|---|
| USD | 0.60 | 1 NZD = 0.60 USD |
| AUD | 0.90 | 1 NZD = 0.90 AUD |
| CNY | 4.00 | 1 NZD = 4.00 CNY |

A computed field `nzd_per_unit` auto-inverts for COGS calculations (e.g. 1 USD = 1.6667 NZD).

### Freight

Flat rate: $100 per CBM. Configured on `forecast.config.freight_rate_cbm`. Not modelled as variable for now — will become accurate post-cartonisation project and 3PL migration.

### Scenario Engine

Scenarios are full config duplicates with driver overrides:

- `volume_adjustment_pct` — adjusts ROQ unit forecast (e.g. -20% for pessimistic)
- `freight_rate_cbm` — override freight assumption
- FX rates — per-scenario (can model NZD weakness)

"Duplicate as Scenario" button on config form creates a copy for what-if analysis.

---

## Product-Level Fields Required

These custom fields are needed on `product.template`. Check if they already exist under different technical names in our stack before creating new ones:

| Field | Expected Technical Name | Type | Source |
|---|---|---|---|
| Brand | `x_brand` | Selection or Char | May already exist on product or category |
| CBM per Unit | `x_cbm_per_unit` | Float | From packaging specs / cartonisation project |
| Tariff Rate % | `x_tariff_rate` | Float | From HS code classification / customs module |
| 3PL Pick Rate | `x_3pl_pick_rate` | Float (NZD) | From Mainfreight rate card |

If brand is resolved via product category hierarchy, the `_resolve_brand()` method in the wizard handles this — adapt to match our actual data model.

---

## Integration Points

### ROQ → Financial (Demand Interface)

The financial wizard's `_get_demand_forecast()` method has two paths:

1. **ROQ path** (commented out in scaffold) — uncomment and wire to actual ROQ forecast model
2. **Sale history fallback** — uses `sale.order.line` trailing 12 months

The ROQ path should be activated once integrated. The demand interface contract (list of dicts above) is the bridge — keep it clean so future demand sources (manual entry, service adapters) can plug in.

### Supplier Info → COGS

`_get_supplier_info()` pulls FOB cost and currency from `product.supplierinfo`. Verify this matches our supplier data structure — we may have multiple suppliers per product with different currencies.

### Pricelists → Revenue

`_get_sell_price()` uses customer pricelists. Verify pricelist assignment on our retail partners (Briscoes, Harvey Norman, Animates, PetStock) is accurate.

---

## Supplier Payment Timing Model

Cash flow accuracy depends on modelling the actual payment chain per supplier. This is NOT a Phase 2 item — it should be built into the core financial module from the start.

### Payment Chain

```
PO placed ──→ Deposit due (immediate or N days)
    │
    ↓  (production lead time)
    │
BL issued ──→ Balance contractually due (but NOT when we actually pay)
    │
    ↓  (transit time from origin port)
    │
Arrival at NZ port ──→ Balance ACTUALLY paid (our real behaviour)
    │
    ↓  (~20 working days)
    │
Customs clearance ──→ Duty + import tax due (rate from forecast.config.tax_id)
```

**Key nuance:** We delay BL balance payment until cargo arrives at port, NOT when the BL is issued. This buys ~3 weeks of float per shipment. The model must use arrival date, not BL date, as the balance payment trigger.

### Supplier Payment Config Model: `forecast.supplier.term`

Editable in the GUI, per-supplier configuration:

| Field | Type | Description |
|---|---|---|
| `supplier_id` | Many2one (res.partner) | Factory / supplier |
| `deposit_pct` | Float | Deposit as % of FOB. Typically 30 or 0 |
| `deposit_trigger_days` | Integer | Days after PO placement deposit is due. Default 0 (immediate) |
| `production_lead_days` | Integer | Production lead time in calendar days |
| `origin_port_id` | Many2one (forecast.origin.port) | FOB port — drives transit time |
| `payment_method` | Selection | TT / LC (LC adds bank processing time) |
| `notes` | Char | |

### Origin Port Transit Config: `forecast.origin.port`

Per-port transit time to NZ, editable in GUI:

| Field | Type | Description |
|---|---|---|
| `name` | Char | Port name (e.g. Shanghai, Ningbo, Shenzhen/Yantian) |
| `country_id` | Many2one (res.country) | |
| `transit_days_nz` | Integer | Sea transit days to NZ port. Shanghai ~22, Ningbo ~20, Shenzhen ~18 |
| `notes` | Char | |

This aligns with the FOB port-based consolidation logic already in the ROQ module — ideally reuse the same port records.

### Cash Flow Timing Calculation

For each COGS line, the cash outflow dates are:

| Event | Date Calculation | Amount |
|---|---|---|
| Deposit | `po_date + deposit_trigger_days` | `FOB_NZD × deposit_pct / 100` |
| Balance | `po_date + production_lead_days + transit_days_nz` (arrival) | `FOB_NZD × (1 - deposit_pct / 100)` |
| Freight | Arrival date (paid on delivery to port) | `freight_total_nzd` |
| Duty + Import Tax | `arrival_date + 20 working days` | `duty + (CIF × import_tax_rate)` |

Where `po_date` is derived backwards from the sale month:
```
po_date = sale_month_start - production_lead_days - transit_days_nz - buffer
```

This means the cash flow engine needs to place outflows in months that may precede the sale month by 2-4 months, depending on the supplier's lead time and port.

### Example: Shanghai supplier, 30% deposit

```
Sale month:         July 2026
Transit (Shanghai): 22 days
Production lead:    45 days
Total lead:         67 days → PO placed ~late April

Cash outflows:
  April:  30% deposit
  July:   70% balance (arrival at NZ port)
  August: Duty + import tax (20 working days post-arrival)

Cash inflow:
  August: Customer receipt (e.g. Briscoes pays last day of following month)
```

This reveals a ~4 month cash gap between deposit and receipt — critical for capital planning.

---

## Cash Flow Model — Phase 2 Backlog

Remaining simplifications to address after the supplier timing model is live:

1. **Import tax refund** — import tax (GST/VAT per `forecast.config.tax_id`) is reclaimable via tax returns with ~2 month lag. Add a tax refund inflow line to the cash flow model. Refund timing should be configurable per-company as return filing frequency varies by jurisdiction (monthly, bi-monthly, quarterly).

2. **Storage costs** — v1 has 3PL pick rate only. Add pallet storage ($/pallet/month from Mainfreight rate card) based on inventory holding forecast.

3. **Seasonality** — v1 distributes demand evenly across months. Pull seasonal weighting from ROQ or allow manual monthly distribution curves per brand/category.

4. **LC timing** — if any suppliers are on letters of credit, add bank processing time (~5-10 days) to the balance payment trigger.

---

## Views & UX

### Menu Structure

```
Forecasting (top-level app)
├── Demand Planning          # from mml_forecast_demand
│   ├── ROQ Dashboard
│   ├── Reorder Quantities
│   └── Demand Signals
├── Financial Planning       # from mml_forecast_financial
│   ├── All Forecasts        # forecast.config list/form
│   └── Analysis
│       ├── P&L Summary      # pivot + graph
│       ├── Cash Flow         # list + line graph
│       ├── Revenue Detail    # list + pivot (brand × month)
│       └── COGS Detail       # list + pivot (waterfall)
```

### Config Form

Single form with tabbed config:
- **FX Rates** — inline editable list
- **Supplier Payment Terms** — inline editable list (deposit %, lead times, origin port)
- **Customer Payment Terms** — inline editable list
- **Operating Expenses** — inline editable list (fixed + variable)
- **P&L Summary** — read-only generated output (tree with column sums)
- **Cash Flow** — read-only generated output
- **Revenue Detail** — read-only drill-down
- **COGS Detail** — read-only waterfall drill-down

Generate button on header triggers full computation pipeline. Reset clears generated data. Lock prevents edits.

---

## Refactoring Notes for Claude Code

When evaluating the scaffold:

1. **Check field naming conventions** against our existing codebase (do we prefix with `x_` or use a module prefix?)
2. **Check if `mail.thread` / `mail.activity.mixin`** is our standard for transactional models or if we reserve it for specific model types
3. **Verify Odoo 19 API compatibility** — the scaffold uses standard ORM patterns but check `invisible` attribute syntax (Odoo 17+ changed from `attrs` to direct `invisible`/`readonly` attributes on fields in views)
4. **The wizard's `_generate_cashflow_lines()` method needs a full rewrite** to implement the supplier payment timing model described above — the scaffold version is a v0 simplification that assumes outflows align with sale month. The rewrite should back-calculate PO dates from sale months using supplier lead times + port transit days, then place deposit/balance/duty outflows in the correct months.

5. **Import tax rate must pull from Odoo's native `account.tax`**, not hardcode 15%. The scaffold has `cif * 0.15` — this must be replaced with a lookup against the company's purchase tax configuration. This is critical for SaaS viability: NZ is 15% GST, Australia is 10% GST, UK is 20% VAT, etc. The lookup pattern:

```python
gst_tax = self.env['account.tax'].search([
    ('type_tax_use', '=', 'purchase'),
    ('amount', '=', company_gst_rate),  # or filter by tax group
    ('company_id', '=', config.company_id.id),
], limit=1)
```

Ideally, add a `tax_id` field on `forecast.config` (Many2one to `account.tax`) so the user explicitly selects which import tax applies to the forecast. This avoids ambiguity in multi-tax environments and makes the config self-documenting.