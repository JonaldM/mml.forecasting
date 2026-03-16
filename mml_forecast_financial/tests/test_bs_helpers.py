"""
Pure-Python tests for BS computation helpers.
These helpers are extracted as module-level functions so they can be tested
without Odoo. The wizard calls these functions internally.

Run: pytest mml_forecast_financial/tests/test_bs_helpers.py -q
"""
from mml_forecast_financial.models.forecast_config_ext import effective_value


class TestEffectiveValue:
    def test_returns_auto_when_override_false(self):
        assert effective_value(auto=10_000.0, manual=99_000.0, override=False) == 10_000.0

    def test_returns_manual_when_override_true(self):
        assert effective_value(auto=10_000.0, manual=99_000.0, override=True) == 99_000.0

    def test_zero_auto_no_override(self):
        assert effective_value(auto=0.0, manual=5_000.0, override=False) == 0.0

    def test_zero_manual_with_override(self):
        assert effective_value(auto=8_000.0, manual=0.0, override=True) == 0.0


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
