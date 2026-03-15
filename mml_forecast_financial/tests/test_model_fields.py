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
