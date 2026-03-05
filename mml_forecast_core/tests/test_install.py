from datetime import date
from odoo.tests.common import TransactionCase


class TestCoreInstall(TransactionCase):

    def test_models_exist(self):
        self.assertTrue(self.env['forecast.config'])
        self.assertTrue(self.env['forecast.fx.rate'])
        self.assertTrue(self.env['forecast.customer.term'])
        self.assertTrue(self.env['forecast.supplier.term'])
        self.assertTrue(self.env['forecast.origin.port'])

    def test_origin_port_has_transit_days(self):
        port = self.env['forecast.origin.port'].create({
            'code': 'TSTHA',
            'name': 'Test Harbour',
            'transit_days_nz': 22,
        })
        self.assertEqual(port.transit_days_nz, 22)

    def test_origin_port_code_uppercased(self):
        port = self.env['forecast.origin.port'].create({
            'code': 'cnsha',
            'name': 'Shanghai Lower',
            'transit_days_nz': 22,
        })
        self.assertEqual(port.code, 'CNSHA')

    def test_forecast_config_has_tax_id_field(self):
        config = self.env['forecast.config'].new({
            'name': 'Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        self.assertIn('tax_id', config._fields)

    def test_forecast_config_has_supplier_term_ids_field(self):
        config = self.env['forecast.config'].new({
            'name': 'Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        self.assertIn('supplier_term_ids', config._fields)

    def test_supplier_term_links_to_port(self):
        port = self.env['forecast.origin.port'].create({
            'code': 'CNNGB', 'name': 'Ningbo', 'transit_days_nz': 20,
        })
        config = self.env['forecast.config'].create({
            'name': 'Test Config',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        supplier = self.env['res.partner'].create({
            'name': 'Test Factory', 'supplier_rank': 1,
        })
        term = self.env['forecast.supplier.term'].create({
            'config_id': config.id,
            'supplier_id': supplier.id,
            'deposit_pct': 30.0,
            'production_lead_days': 45,
            'origin_port_id': port.id,
        })
        self.assertEqual(term.transit_days, 20)
        self.assertEqual(term.total_lead_days, 65)

    def test_customer_term_end_of_following(self):
        config = self.env['forecast.config'].create({
            'name': 'Term Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        partner = self.env['res.partner'].create({'name': 'Test Customer'})
        term = self.env['forecast.customer.term'].create({
            'config_id': config.id,
            'partner_id': partner.id,
            'rule_type': 'end_of_following',
        })
        # Invoice Jan 15 -> receipt = last day of Feb
        receipt = term.compute_receipt_date(date(2026, 1, 15))
        self.assertEqual(receipt, date(2026, 2, 28))

    def test_fx_rate_nzd_per_unit_inversion(self):
        config = self.env['forecast.config'].create({
            'name': 'FX Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if not usd:
            return  # skip if USD not installed
        rate = self.env['forecast.fx.rate'].create({
            'config_id': config.id,
            'currency_id': usd.id,
            'rate_to_nzd': 0.60,
        })
        self.assertAlmostEqual(rate.nzd_per_unit, 1.0 / 0.60, places=4)
