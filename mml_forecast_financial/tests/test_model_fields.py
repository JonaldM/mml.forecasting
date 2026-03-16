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


class TestCashflowLineFobSplit:
    def test_payments_fob_deposit_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_cashflow_line')
        cls = mod.ForecastCashflowLine
        assert 'payments_fob_deposit' in cls._fields_meta

    def test_payments_fob_balance_field_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_cashflow_line')
        cls = mod.ForecastCashflowLine
        assert 'payments_fob_balance' in cls._fields_meta


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


class TestConfigExtNewFields:
    def test_company_id_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'company_id' in cls._fields_meta

    def test_opening_balance_flat_fields_defined(self):
        """Representative check — cash group. Same pattern exists for all 5 groups."""
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        for field in ('opening_cash', 'override_cash', 'opening_cash_manual', 'effective_cash'):
            assert field in cls._fields_meta, f'missing {field}'

    def test_opening_balance_pulled_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'opening_balance_pulled' in cls._fields_meta

    def test_kpi_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        for field in ('kpi_total_revenue', 'kpi_ebitda', 'kpi_total_cogs',
                      'kpi_ending_cash', 'kpi_cash_low_value', 'kpi_cash_low_month'):
            assert field in cls._fields_meta, f'missing {field}'

    def test_setup_boolean_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        for field in ('setup_period_done', 'setup_fx_done', 'setup_terms_done',
                      'setup_ob_done', 'setup_opex_done'):
            assert field in cls._fields_meta, f'missing {field}'

    def test_balance_sheet_line_ids_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'balance_sheet_line_ids' in cls._fields_meta

    def test_variance_line_ids_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'variance_line_ids' in cls._fields_meta

    def test_opening_balance_ids_removed(self):
        """After flattening, the old One2many must not exist on this model."""
        mod = _import_model('mml_forecast_financial.models.forecast_config_ext')
        cls = mod.ForecastConfigFinancialExt
        assert 'opening_balance_ids' not in cls._fields_meta


# ---------------------------------------------------------------------------
# Fake record helpers for testing compute methods without ORM
# ---------------------------------------------------------------------------

class _FakeRec:
    """Minimal duck-typed record for testing compute methods.

    Supports `for rec in self` iteration (yields self) and attribute assignment.
    Satisfies the `for rec in self: rec.field = value` pattern used in Odoo computes.
    """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __iter__(self):
        yield self

    def __bool__(self):
        return True


class _FakeRecordset(list):
    """List subclass that also supports .mapped() and .sorted() for KPI tests."""

    def mapped(self, field):
        return [getattr(item, field) for item in self]

    def sorted(self, key):
        import operator
        return sorted(self, key=operator.attrgetter(key))

    def __bool__(self):
        return len(self) > 0


# ---------------------------------------------------------------------------
# TestSetupCompletionBooleans
# ---------------------------------------------------------------------------

class TestSetupCompletionBooleans:
    """Pure-Python tests for _compute_setup_progress.

    Each test verifies one boolean in both False and True states.
    """

    def _run_compute(self, **kwargs):
        """Create a fake record with the given attrs, run the compute, return it."""
        from mml_forecast_financial.models.forecast_config_ext import ForecastConfigFinancialExt
        from datetime import date
        defaults = dict(
            date_start=None,
            fx_rate_ids=_FakeRecordset(),
            customer_term_ids=_FakeRecordset(),
            supplier_term_ids=_FakeRecordset(),
            opening_balance_pulled=False,
            opex_line_ids=_FakeRecordset(),
            # output fields — set to sentinel so we can assert they changed
            setup_period_done=None,
            setup_fx_done=None,
            setup_terms_done=None,
            setup_ob_done=None,
            setup_opex_done=None,
        )
        defaults.update(kwargs)
        rec = _FakeRec(**defaults)
        ForecastConfigFinancialExt._compute_setup_progress(rec)
        return rec

    def test_period_done_false_when_no_date_start(self):
        rec = self._run_compute(date_start=None)
        assert rec.setup_period_done is False

    def test_period_done_true_when_date_set(self):
        from datetime import date
        rec = self._run_compute(date_start=date(2026, 1, 1))
        assert rec.setup_period_done is True

    def test_fx_done_false_when_no_rates(self):
        rec = self._run_compute(fx_rate_ids=_FakeRecordset())
        assert rec.setup_fx_done is False

    def test_fx_done_true_when_rates_exist(self):
        fake_rate = _FakeRec()
        rec = self._run_compute(fx_rate_ids=_FakeRecordset([fake_rate]))
        assert rec.setup_fx_done is True

    def test_terms_done_false_when_no_terms(self):
        rec = self._run_compute(
            customer_term_ids=_FakeRecordset(),
            supplier_term_ids=_FakeRecordset(),
        )
        assert rec.setup_terms_done is False

    def test_terms_done_true_when_customer_terms_exist(self):
        rec = self._run_compute(
            customer_term_ids=_FakeRecordset([_FakeRec()]),
            supplier_term_ids=_FakeRecordset(),
        )
        assert rec.setup_terms_done is True

    def test_terms_done_true_when_supplier_terms_exist(self):
        rec = self._run_compute(
            customer_term_ids=_FakeRecordset(),
            supplier_term_ids=_FakeRecordset([_FakeRec()]),
        )
        assert rec.setup_terms_done is True

    def test_ob_done_false_when_not_pulled(self):
        rec = self._run_compute(opening_balance_pulled=False)
        assert rec.setup_ob_done is False

    def test_ob_done_true_when_pulled(self):
        rec = self._run_compute(opening_balance_pulled=True)
        assert rec.setup_ob_done is True

    def test_opex_done_false_when_no_lines(self):
        rec = self._run_compute(opex_line_ids=_FakeRecordset())
        assert rec.setup_opex_done is False

    def test_opex_done_true_when_lines_exist(self):
        rec = self._run_compute(opex_line_ids=_FakeRecordset([_FakeRec()]))
        assert rec.setup_opex_done is True


# ---------------------------------------------------------------------------
# TestKpiFields
# ---------------------------------------------------------------------------

class TestKpiFields:
    """Pure-Python tests for _compute_kpis."""

    def _run_kpi_compute(self, pnl_lines, cf_lines):
        from mml_forecast_financial.models.forecast_config_ext import ForecastConfigFinancialExt
        rec = _FakeRec(
            pnl_line_ids=_FakeRecordset(pnl_lines),
            cashflow_line_ids=_FakeRecordset(cf_lines),
            kpi_total_revenue=None,
            kpi_ebitda=None,
            kpi_total_cogs=None,
            kpi_ending_cash=None,
            kpi_cash_low_value=None,
            kpi_cash_low_month=None,
        )
        ForecastConfigFinancialExt._compute_kpis(rec)
        return rec

    def test_kpi_fields_zero_when_no_lines(self):
        rec = self._run_kpi_compute(pnl_lines=[], cf_lines=[])
        assert rec.kpi_total_revenue == 0.0
        assert rec.kpi_ebitda == 0.0
        assert rec.kpi_total_cogs == 0.0
        assert rec.kpi_ending_cash == 0.0
        assert rec.kpi_cash_low_value == 0.0
        assert rec.kpi_cash_low_month == ''

    def test_kpi_total_revenue_sums_pnl_lines(self):
        p1 = _FakeRec(revenue=1000.0, ebitda=200.0, total_cogs=300.0)
        p2 = _FakeRec(revenue=2000.0, ebitda=400.0, total_cogs=600.0)
        rec = self._run_kpi_compute(pnl_lines=[p1, p2], cf_lines=[])
        assert rec.kpi_total_revenue == 3000.0
        assert rec.kpi_ebitda == 600.0
        assert rec.kpi_total_cogs == 900.0

    def test_kpi_ending_cash_takes_last_cashflow_line(self):
        # sorted('id') means the line with the highest id is last
        cf1 = _FakeRec(id=1, cumulative_cashflow=500.0, period_label='2026-01')
        cf2 = _FakeRec(id=2, cumulative_cashflow=750.0, period_label='2026-02')
        cf3 = _FakeRec(id=3, cumulative_cashflow=300.0, period_label='2026-03')
        rec = self._run_kpi_compute(pnl_lines=[], cf_lines=[cf3, cf1, cf2])
        assert rec.kpi_ending_cash == 300.0  # last by id

    def test_kpi_cash_low_month_returns_period_label_of_minimum(self):
        cf1 = _FakeRec(id=1, cumulative_cashflow=500.0, period_label='2026-01')
        cf2 = _FakeRec(id=2, cumulative_cashflow=95000.0, period_label='2026-02')
        cf3 = _FakeRec(id=3, cumulative_cashflow=120000.0, period_label='2026-03')
        rec = self._run_kpi_compute(pnl_lines=[], cf_lines=[cf1, cf2, cf3])
        assert rec.kpi_cash_low_value == 500.0
        assert rec.kpi_cash_low_month == '2026-01'

    def test_kpi_cash_low_distinct_from_ending_cash(self):
        """Low point and ending cash can be different months."""
        cf1 = _FakeRec(id=1, cumulative_cashflow=200.0, period_label='2026-01')
        cf2 = _FakeRec(id=2, cumulative_cashflow=50.0, period_label='2026-02')
        cf3 = _FakeRec(id=3, cumulative_cashflow=800.0, period_label='2026-03')
        rec = self._run_kpi_compute(pnl_lines=[], cf_lines=[cf1, cf2, cf3])
        assert rec.kpi_ending_cash == 800.0     # last by id
        assert rec.kpi_cash_low_value == 50.0   # minimum
        assert rec.kpi_cash_low_month == '2026-02'
