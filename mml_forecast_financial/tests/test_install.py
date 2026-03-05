from datetime import date

from odoo.tests.common import TransactionCase


class TestFinancialInstall(TransactionCase):
    """Verify mml_forecast_financial models and relations are correctly wired."""

    def test_models_exist(self):
        models = [
            'forecast.revenue.line',
            'forecast.cogs.line',
            'forecast.pnl.line',
            'forecast.cashflow.line',
            'forecast.opex.line',
        ]
        for m in models:
            self.assertIn(m, self.env, f"Model {m} must exist")

    def test_config_has_financial_one2manys(self):
        """forecast.config must have all financial line one2many fields."""
        config = self.env['forecast.config']
        for field in ('revenue_line_ids', 'cogs_line_ids', 'pnl_line_ids',
                      'cashflow_line_ids', 'opex_line_ids'):
            self.assertIn(field, config._fields, f"forecast.config must have {field}")

    def test_config_has_tax_id(self):
        """forecast.config must have tax_id field."""
        config = self.env['forecast.config']
        self.assertIn('tax_id', config._fields)

    def test_revenue_line_compute(self):
        """forecast.revenue.line computes revenue = units * price."""
        config = self.env['forecast.config'].create({
            'name': 'Test Financial Config',
            'date_start': date(2026, 1, 1),
            'horizon_months': 3,
            'freight_rate_cbm': 100.0,
        })
        product = self.env['product.product'].create({'name': 'Test Product'})
        line = self.env['forecast.revenue.line'].create({
            'config_id': config.id,
            'product_id': product.id,
            'period_start': date(2026, 1, 1),
            'period_label': 'Jan 2026',
            'forecast_units': 100.0,
            'sell_price_unit': 10.0,
        })
        self.assertAlmostEqual(line.revenue, 1000.0, places=2)
