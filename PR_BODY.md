# feat(forecast): enforce ex-GST pricelist in financial forecast wizard

**Compare URL:** https://github.com/JonaldM/mml.forecasting/compare/master...claude-sprint/forecast-gst-constraint?expand=1

## Why

Audit finding #2 from the 2026-04-27 production-readiness review: the financial
forecast wizard previously emitted only a per-product `_logger.warning()` when
generating revenue lines from customer pricelists. If any pricelist on a
forecast customer was misconfigured as GST-inclusive (i.e. the linked tax has
`price_include=True`), the GST component leaked into revenue and overstated
12-month forecasts by ~15% in NZ — a silent, material risk for an executive
P&L and cashflow dashboard.

The fix replaces the soft warning with a hard `ValidationError` that fires
**before** any revenue, COGS, P&L, cashflow, or balance-sheet line is created.

## What

- `mml_forecast_financial/wizards/forecast_generate_wizard.py`
  - Added `ForecastGenerateWizard._validate_pricelists_ex_gst(config)`. The
    validator walks `config.customer_term_ids`, follows each term's
    `partner_id.property_product_pricelist`, and inspects every linked tax
    (both flat `pricelist.tax_ids` and per-item `item_ids.tax_ids`) for
    `price_include=True`.
  - Static helper `_inclusive_taxes_on_pricelist(pricelist)` isolates the
    pricelist tax inspection so it is easy to unit-test.
  - On any offender, the wizard raises `ValidationError` with a multi-line
    message naming each customer + pricelist + offending tax, and pointing the
    user at the `price_include` flag or an ex-GST pricelist swap.
  - The advisory `_logger.warning()` previously inside `_get_sell_price()` is
    removed — by the time we reach price resolution, the upstream gate
    guarantees the pricelist is ex-GST.
  - Wizard's `generate()` now runs the gate as Step 0 before any
    `unlink()`/clear of the prior generated lines.
- `mml_forecast_financial/tests/test_pricelist_gst_constraint.py` (new, 9 tests)
  - Pure-Python tests using duck-typed `_FakePartner` / `_FakePricelist` /
    `_FakeTax` records (no Odoo registry required, runs under the same
    `not odoo_integration` gate as the rest of the structural suite).
  - Covers: empty terms, no pricelist, ex-GST tax, no tax, single GST-inclusive
    pricelist (asserting message contains the customer name, pricelist name,
    `price_include` keyword, and `GST-exclusive` phrasing), multiple
    GST-inclusive pricelists, mixed clean terms, and a regression guard that
    the old warning string no longer appears in `_get_sell_price()`.

A `forecast.config`-level `@api.constrains` is intentionally **not** added —
the constraint at the wizard's entrypoint is the load-bearing one (it fires at
"Generate" time, when the user expects validation), and an `@api.constrains`
hook would block partial mid-edit configurations and create UX friction
without adding safety.

## Test results

```
$ pytest -m "not odoo_integration" -q
.................................................................................
81 passed, 29 deselected in 2.58s
```

Baseline before the change was 72 passing / 29 deselected; the 9 new tests in
`test_pricelist_gst_constraint.py` are additive and no existing test
regressed.

## Test plan

- [x] New unit tests pass (9/9)
- [x] Full pure-Python suite passes (81/81, 29 deselected)
- [ ] Manual smoke on a clone of the live Hetzner DB (see
      `project_mml_odoo19_upgrade_approach` memory for the Playwright +
      replica DB workflow): create a forecast pointing at a customer with a
      GST-inclusive pricelist and confirm the wizard fails with the new
      message rather than emitting silent warnings into the log.
- [ ] Verify the error message renders cleanly in the Odoo UI (the validator
      builds a multi-line string; Odoo should display it in the standard
      red-banner notification).
