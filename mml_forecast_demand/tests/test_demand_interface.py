import calendar
from datetime import date

from odoo.tests.common import TransactionCase


class TestDemandInterface(TransactionCase):
    """Verify roq.forecast.run exposes the standard demand interface."""

    def test_method_exists(self):
        """get_demand_forecast method must exist on roq.forecast.run."""
        model = self.env['roq.forecast.run']
        self.assertTrue(
            hasattr(model, 'get_demand_forecast'),
            "roq.forecast.run must have get_demand_forecast method",
        )

    def test_returns_list(self):
        """get_demand_forecast returns a list (even if empty)."""
        run = self.env['roq.forecast.run'].create({})
        result = run.get_demand_forecast(date(2026, 1, 1), 3)
        self.assertIsInstance(result, list)

    def test_empty_run_returns_empty_list(self):
        """A run with no lines returns an empty list."""
        run = self.env['roq.forecast.run'].create({})
        result = run.get_demand_forecast(date(2026, 1, 1), 12)
        self.assertEqual(result, [])

    def test_result_dict_keys(self):
        """Each returned dict contains all required interface keys."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Interface Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.assertTrue(warehouse, "Need at least one warehouse for this test")
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': 10.0,
        })
        result = run.get_demand_forecast(date(2026, 4, 1), 1)
        self.assertEqual(len(result), 1)
        row = result[0]
        expected_keys = {
            'product_id', 'partner_id', 'period_start',
            'period_label', 'forecast_units', 'brand', 'category',
        }
        self.assertEqual(set(row.keys()), expected_keys)

    def test_forecast_units_converts_weekly_to_monthly(self):
        """forecast_units = forecasted_weekly_demand * days_in_month / 7."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Conversion Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        weekly_demand = 14.0
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': weekly_demand,
        })
        # April 2026 has 30 days
        result = run.get_demand_forecast(date(2026, 4, 1), 1)
        self.assertEqual(len(result), 1)
        days_in_april = calendar.monthrange(2026, 4)[1]  # 30
        expected = weekly_demand * days_in_april / 7.0
        self.assertAlmostEqual(result[0]['forecast_units'], expected, places=5)

    def test_horizon_produces_correct_month_count(self):
        """Result contains one entry per line per month in the horizon."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Horizon Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': 5.0,
        })
        horizon = 6
        result = run.get_demand_forecast(date(2026, 1, 1), horizon)
        self.assertEqual(len(result), horizon)

    def test_period_label_format(self):
        """period_label is formatted as 'Mon YYYY' (e.g. 'Apr 2026')."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Label Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': 1.0,
        })
        result = run.get_demand_forecast(date(2026, 4, 1), 1)
        self.assertEqual(result[0]['period_label'], 'Apr 2026')

    def test_partner_id_is_supplier_id(self):
        """partner_id in result is the supplier_id from the forecast line."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Supplier Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        supplier = self.env['res.partner'].create({'name': 'Test Supplier', 'supplier_rank': 1})
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'supplier_id': supplier.id,
            'forecasted_weekly_demand': 3.0,
        })
        result = run.get_demand_forecast(date(2026, 1, 1), 1)
        self.assertEqual(result[0]['partner_id'], supplier.id)

    def test_no_supplier_returns_false_partner_id(self):
        """partner_id is False when the line has no supplier_id."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'No Supplier SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': 2.0,
        })
        result = run.get_demand_forecast(date(2026, 1, 1), 1)
        self.assertIs(result[0]['partner_id'], False)

    def test_date_start_normalised_to_month_start(self):
        """date_start mid-month is treated as the 1st of that month."""
        run = self.env['roq.forecast.run'].create({})
        product = self.env['product.product'].create({'name': 'Normalise Test SKU'})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['roq.forecast.line'].create({
            'run_id': run.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'forecasted_weekly_demand': 7.0,
        })
        # Passing the 15th should still yield period_start on the 1st
        result = run.get_demand_forecast(date(2026, 4, 15), 1)
        self.assertEqual(result[0]['period_start'], date(2026, 4, 1))
