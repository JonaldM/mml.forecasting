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


class TestForecastOpeningBalance:
    def test_all_auto_fields_defined(self):
        mod = _import_model('mml_forecast_financial.models.forecast_opening_balance')
        cls = mod.ForecastOpeningBalance
        for item in ('cash', 'receivables', 'inventory', 'payables', 'equity'):
            assert f'opening_{item}' in cls._fields_meta, f'missing opening_{item}'
            assert f'override_{item}' in cls._fields_meta, f'missing override_{item}'
            assert f'effective_{item}' in cls._fields_meta, f'missing effective_{item}'


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
