import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


def _safe_int(val, default):
    try:
        return int(val) if val not in (None, '', False) else default
    except (ValueError, TypeError):
        return default


def _safe_float(val, default):
    try:
        return float(val) if val not in (None, '', False) else default
    except (ValueError, TypeError):
        return default

RUN_STATUS = [
    ('draft', 'Draft'),
    ('running', 'Running'),
    ('complete', 'Complete'),
    ('error', 'Error'),
]


class RoqForecastRun(models.Model):
    _name = 'roq.forecast.run'
    _description = 'ROQ Forecast Run'
    _order = 'run_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        default=lambda self: (
            self.env['ir.sequence'].next_by_code('roq.forecast.run')
            or fields.Date.today().strftime('ROQ-%Y-W%W')
        ),
    )
    run_date = fields.Datetime(string='Run Date', default=fields.Datetime.now, readonly=True)
    status = fields.Selection(RUN_STATUS, default='draft', required=True)

    # Parameter snapshots — immutable after run completes, for audit
    lookback_weeks = fields.Integer(string='Lookback Weeks (Snapshot)')
    sma_window_weeks = fields.Integer(string='SMA Window (Snapshot)')
    default_lead_time_days = fields.Integer(string='Default Lead Time (Snapshot)')
    default_review_interval_days = fields.Integer(string='Default Review Interval (Snapshot)')
    default_service_level = fields.Float(string='Default Service Level (Snapshot)', digits=(4, 3))

    # Summary stats
    total_skus_processed = fields.Integer(string='SKUs Processed', readonly=True)
    total_skus_reorder = fields.Integer(string='SKUs with ROQ > 0', readonly=True)
    total_skus_oos_risk = fields.Integer(string='SKUs at OOS Risk', readonly=True)

    enable_moq_enforcement = fields.Boolean(
        string='MOQ Enforcement Active', default=True,
        help='Parameter snapshot: was MOQ enforcement active for this run.',
    )

    line_ids = fields.One2many('roq.forecast.line', 'run_id', string='Result Lines')
    shipment_group_ids = fields.One2many(
        'roq.shipment.group', 'run_id', string='Shipment Groups',
    )
    supplier_order_line_ids = fields.One2many(
        'roq.shipment.group.line', 'run_id', string='Supplier Order Lines',
        help='All supplier lines from shipment groups created by this run.',
    )
    notes = fields.Text(string='Run Log / Errors')

    @api.model
    def cron_run_weekly_roq(self):
        """Called by ir.cron weekly trigger."""
        # Warn if the sequence is missing — the name field fallback will handle it,
        # but this makes the misconfiguration visible in the server log immediately.
        if not self.env['ir.sequence'].search([('code', '=', 'roq.forecast.run')], limit=1):
            _logger.warning(
                "ROQ: ir.sequence with code 'roq.forecast.run' not found — "
                "falling back to date-based reference. Install sequence data to fix."
            )
        run = self.create({})
        run.action_run()

    def action_run(self):
        """User-triggered or cron-triggered ROQ run."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.AccessError(_('Only system administrators can trigger ROQ runs manually.'))
        from ..services.roq_pipeline import RoqPipeline
        # Snapshot current settings on the run header
        get = self.env['ir.config_parameter'].sudo().get_param
        self.write({
            'lookback_weeks': _safe_int(get('roq.lookback_weeks'), 156),
            'sma_window_weeks': _safe_int(get('roq.sma_window_weeks'), 52),
            'default_lead_time_days': _safe_int(get('roq.default_lead_time_days'), 100),
            'default_review_interval_days': _safe_int(get('roq.default_review_interval_days'), 30),
            'default_service_level': _safe_float(get('roq.default_service_level'), 0.97),
            'enable_moq_enforcement': get('roq.enable_moq_enforcement', 'True') == 'True',
        })
        pipeline = RoqPipeline(self.env)
        pipeline.run(self)
        self.env['mml.event'].emit(
            'roq.forecast.run',
            quantity=1,
            billable_unit='roq_run',
            res_model=self._name,
            res_id=self.id,
            source_module='mml_roq_forecast',
            payload={'run_ref': self.name, 'sku_count': len(self.line_ids)},
        )

    def get_demand_forecast(self, date_start, horizon_months):
        """
        Return demand forecast data as a list of dicts.

        This is the standard demand interface consumed by mml_forecast_financial.
        Decouples the financial module from roq internals.

        The ROQ model stores a single forward-looking ``forecasted_weekly_demand``
        per SKU/warehouse line (not a time-series). This method projects that
        weekly rate into monthly units for each month in the horizon, using the
        actual number of days in each month to convert (days / 7 × weekly_demand).

        Args:
            date_start (date): First day of the forecast period (will be normalised
                to the 1st of the month if not already).
            horizon_months (int): Number of months to include.

        Returns:
            list[dict]: Each dict has keys:
                product_id (int): product.product ID
                partner_id (int or False): res.partner ID (supplier for this line)
                period_start (date): First day of the month
                period_label (str): e.g. "Apr 2026"
                forecast_units (float): Units expected to sell in that month
                brand (str): product category name or ''
                category (str): product category complete name or ''
        """
        from dateutil.relativedelta import relativedelta
        import calendar

        self.ensure_one()
        result = []

        # Build ordered list of month start dates in the horizon
        months = []
        d = date_start.replace(day=1)
        for _ in range(horizon_months):
            months.append(d)
            d += relativedelta(months=1)

        for line in self.line_ids:
            weekly_demand = line.forecasted_weekly_demand or 0.0
            product = line.product_id
            brand = product.categ_id.name if product.categ_id else ''
            category = product.categ_id.complete_name if product.categ_id else ''
            partner_id = line.supplier_id.id if line.supplier_id else False

            for period_start in months:
                days_in_month = calendar.monthrange(period_start.year, period_start.month)[1]
                forecast_units = weekly_demand * days_in_month / 7.0

                result.append({
                    'product_id': product.id,
                    'partner_id': partner_id,
                    'period_start': period_start,
                    'period_label': period_start.strftime('%b %Y'),
                    'forecast_units': forecast_units,
                    'brand': brand,
                    'category': category,
                })

        return result
