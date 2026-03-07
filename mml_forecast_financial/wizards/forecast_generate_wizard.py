import logging
import math
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import models, api

_logger = logging.getLogger(__name__)


class ForecastGenerateWizard(models.TransientModel):
    _name = 'forecast.generate.wizard'
    _description = 'Forecast Generation Engine'

    @api.model
    def generate(self, config):
        """
        Main forecast generation pipeline.

        Steps:
            1. Build month buckets
            2. Pull demand forecast (ROQ or sale history)
            3. Build revenue lines
            4. Build COGS waterfall lines
            5. Aggregate to P&L summary
            6. Compute cash flow timing
        """
        # Clear previous generated data
        config.revenue_line_ids.unlink()
        config.cogs_line_ids.unlink()
        config.pnl_line_ids.unlink()
        config.cashflow_line_ids.unlink()

        months = self._build_month_buckets(config)
        demand = self._get_demand_forecast(config, months)

        if not demand:
            _logger.warning('No demand data found for forecast %s', config.name)
            return

        revenue_lines = self._generate_revenue_lines(config, demand)
        cogs_lines = self._generate_cogs_lines(config, demand)
        self._generate_pnl_lines(config, months, revenue_lines, cogs_lines)
        self._generate_cashflow_lines(config, months, revenue_lines, cogs_lines)

    # -------------------------------------------------------------------------
    # Month buckets
    # -------------------------------------------------------------------------
    def _build_month_buckets(self, config):
        """Return list of (period_start, period_label) tuples."""
        months = []
        current = config.date_start.replace(day=1)
        for _ in range(config.horizon_months):
            label = current.strftime('%Y-%m')
            months.append((current, label))
            current += relativedelta(months=1)
        return months

    # -------------------------------------------------------------------------
    # Demand forecast
    # -------------------------------------------------------------------------
    def _get_demand_forecast(self, config, months):
        """
        Pull unit forecast data.

        Returns list of dicts:
        [
            {
                'product_id': int,
                'partner_id': int,
                'period_start': date,
                'period_label': str,
                'forecast_units': float,
                'brand': str,
                'category': str,
            },
            ...
        ]

        Strategy:
            1. Try ROQ forecast model if mml_forecast_demand is installed
            2. Fallback: use trailing 12-month sale order lines as proxy
        """
        demand = []

        # --- Strategy 1: ROQ module (mml_forecast_demand) ---
        ForecastRun = self.env.get('roq.forecast.run')
        if ForecastRun is not None:
            runs = ForecastRun.search(
                [('status', '=', 'complete')], order='create_date desc', limit=1
            )
            if runs:
                demand_data = runs.get_demand_forecast(
                    config.date_start, config.horizon_months
                )
                if demand_data:
                    _logger.info(
                        'Pulled %d demand records from ROQ run %s',
                        len(demand_data), runs.id,
                    )
                    return demand_data

        # --- Strategy 2: Trailing sale history as proxy ---
        demand = self._demand_from_sale_history(config, months)
        return demand

    def _demand_from_sale_history(self, config, months):
        """
        Use trailing 12-month confirmed sale order lines as demand proxy.
        Distributes historical monthly averages across forecast months.
        Applies volume_adjustment_pct from config.
        """
        demand = []
        SaleOrderLine = self.env['sale.order.line']

        # Lookback: 12 months prior to forecast start
        lookback_start = config.date_start - relativedelta(months=12)
        lookback_end = config.date_start

        lines = SaleOrderLine.search([
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', lookback_start),
            ('order_id.date_order', '<', lookback_end),
        ])

        # Aggregate: (product, partner) -> monthly avg units
        agg = defaultdict(lambda: {'total_qty': 0.0, 'months_seen': set()})
        for line in lines:
            key = (line.product_id.id, line.order_partner_id.id)
            order_month = line.order_id.date_order.strftime('%Y-%m')
            agg[key]['total_qty'] += line.product_uom_qty
            agg[key]['months_seen'].add(order_month)
            agg[key]['product'] = line.product_id
            agg[key]['partner'] = line.order_partner_id

        vol_adj = 1.0 + (config.volume_adjustment_pct / 100.0)

        for (product_id, partner_id), data in agg.items():
            # Monthly average = total / 12 (full lookback)
            monthly_avg = (data['total_qty'] / 12.0) * vol_adj
            product = data['product']

            # Resolve brand from product category or tags
            brand = self._resolve_brand(product)
            category = (
                product.categ_id.name if product.categ_id else 'Uncategorised'
            )

            for period_start, period_label in months:
                demand.append({
                    'product_id': product_id,
                    'partner_id': partner_id,
                    'period_start': period_start,
                    'period_label': period_label,
                    'forecast_units': monthly_avg,
                    'brand': brand,
                    'category': category,
                })

        _logger.info(
            'Generated %d demand lines from sale history (%d product-customer combos)',
            len(demand), len(agg),
        )
        return demand

    def _resolve_brand(self, product):
        """
        Resolve brand string from product.
        Checks product category hierarchy or a custom field.
        Override this to match your product data model.
        """
        # Option 1: Custom field on product template
        if hasattr(product.product_tmpl_id, 'x_brand'):
            return product.product_tmpl_id.x_brand or 'Unknown'

        # Option 2: Top-level product category as brand proxy
        categ = product.categ_id
        while categ.parent_id:
            categ = categ.parent_id
        return categ.name if categ else 'Unknown'

    # -------------------------------------------------------------------------
    # Revenue generation
    # -------------------------------------------------------------------------
    def _generate_revenue_lines(self, config, demand):
        """Create forecast.revenue.line records from demand data."""
        RevenueLine = self.env['forecast.revenue.line']
        lines_data = []

        for d in demand:
            product = self.env['product.product'].browse(d['product_id'])
            partner = self.env['res.partner'].browse(d['partner_id'])

            # Get sell price: try pricelist, fallback to list price
            sell_price = self._get_sell_price(product, partner)

            lines_data.append({
                'config_id': config.id,
                'period_start': d['period_start'],
                'period_label': d['period_label'],
                'product_id': d['product_id'],
                'partner_id': d['partner_id'],
                'brand': d['brand'],
                'category': d['category'],
                'forecast_units': d['forecast_units'],
                'sell_price_unit': sell_price,
            })

        lines = RevenueLine.create(lines_data)
        _logger.info('Created %d revenue lines', len(lines))
        return lines

    def _get_sell_price(self, product, partner):
        """
        Resolve sell price for a product-customer pair.
        Priority: customer pricelist → product list_price.
        """
        # Safe pricelist price lookup for Odoo 17+
        # property_product_pricelist was moved to sale_management in Odoo 17.
        # _get_product_price() no longer accepts a partner argument from Odoo 17.
        try:
            pricelist = getattr(partner, 'property_product_pricelist', None)
            if pricelist:
                price = pricelist._get_product_price(product, 1.0)
                if price:
                    return price
        except (AttributeError, TypeError):
            pass
        return product.list_price or 0.0

    # -------------------------------------------------------------------------
    # COGS generation
    # -------------------------------------------------------------------------
    def _generate_cogs_lines(self, config, demand):
        """Create forecast.cogs.line records with full waterfall."""
        CogsLine = self.env['forecast.cogs.line']
        lines_data = []

        fx_rates = config.fx_rate_ids

        for d in demand:
            product = self.env['product.product'].browse(d['product_id'])
            tmpl = product.product_tmpl_id

            # Supplier info: FOB cost, currency
            supplier_info = self._get_supplier_info(product)
            fob_fcy = supplier_info.get('price', 0.0)
            fob_currency = supplier_info.get('currency', 'USD')

            # FX conversion
            fx_rate = fx_rates.get_rate(fob_currency) if fx_rates else 1.0

            # CBM per unit (custom field or fallback)
            cbm = getattr(tmpl, 'x_cbm_per_unit', 0.0) or 0.0

            # Tariff rate (custom field or fallback)
            tariff = getattr(tmpl, 'x_tariff_rate', 0.0) or 0.0

            # 3PL pick rate (could be product-level or global config)
            tpl_rate = getattr(tmpl, 'x_3pl_pick_rate', 0.0) or 0.0

            lines_data.append({
                'config_id': config.id,
                'period_start': d['period_start'],
                'period_label': d['period_label'],
                'product_id': d['product_id'],
                'partner_id': d['partner_id'],
                'brand': d['brand'],
                'category': d['category'],
                'forecast_units': d['forecast_units'],
                'fob_unit_fcy': fob_fcy,
                'fob_currency': fob_currency,
                'fx_rate_applied': fx_rate,
                'cbm_per_unit': cbm,
                'freight_rate_cbm': config.freight_rate_cbm,
                'tariff_rate_pct': tariff,
                'tpl_pick_rate': tpl_rate,
            })

        lines = CogsLine.create(lines_data)
        _logger.info('Created %d COGS lines', len(lines))
        return lines

    def _get_supplier_info(self, product):
        """Get primary supplier price and currency for a product."""
        info = product.seller_ids.sorted('sequence')[:1]
        if info:
            return {
                'price': info.price,
                'currency': info.currency_id.name if info.currency_id else 'NZD',
            }
        return {'price': 0.0, 'currency': 'NZD'}

    # -------------------------------------------------------------------------
    # P&L aggregation
    # -------------------------------------------------------------------------
    def _generate_pnl_lines(self, config, months, revenue_lines, cogs_lines):
        """Aggregate revenue and COGS into monthly P&L summaries."""
        PnlLine = self.env['forecast.pnl.line']
        lines_data = []

        for period_start, period_label in months:
            # Revenue for this month
            month_rev = revenue_lines.filtered(
                lambda r: r.period_start == period_start
            )
            total_revenue = sum(month_rev.mapped('revenue'))

            # COGS for this month
            month_cogs = cogs_lines.filtered(
                lambda r: r.period_start == period_start
            )
            cogs_fob = sum(month_cogs.mapped('fob_total_nzd'))
            cogs_freight = sum(month_cogs.mapped('freight_total_nzd'))
            cogs_duty = sum(month_cogs.mapped('duty_total_nzd'))
            cogs_3pl = sum(month_cogs.mapped('tpl_total_nzd'))

            # OpEx
            opex_fixed = 0.0
            opex_variable = 0.0
            for opex in config.opex_line_ids:
                if opex.cost_type == 'fixed':
                    opex_fixed += opex.monthly_amount or 0.0
                else:
                    opex_variable += total_revenue * (opex.pct_of_revenue / 100.0)

            lines_data.append({
                'config_id': config.id,
                'period_start': period_start,
                'period_label': period_label,
                'revenue': total_revenue,
                'cogs_fob': cogs_fob,
                'cogs_freight': cogs_freight,
                'cogs_duty': cogs_duty,
                'cogs_3pl': cogs_3pl,
                'opex_fixed': opex_fixed,
                'opex_variable': opex_variable,
            })

        lines = PnlLine.create(lines_data)
        _logger.info('Created %d P&L summary lines', len(lines))
        return lines

    # -------------------------------------------------------------------------
    # Cash flow timing
    # -------------------------------------------------------------------------
    def _generate_cashflow_lines(self, config, months, revenue_lines, cogs_lines):
        """
        Build monthly cash flow with correct supplier payment timing.

        Outflow timing (per sale month M — goods must arrive before M):
          - Deposit: paid at PO placement → month M minus ceil(deposit_trigger_days / 30)
          - Balance: paid at bill of lading → month M minus ceil(transit_days / 30)
          - Freight: paid same month as balance (to freight forwarder on shipment)
          - GST/duty: paid to customs on arrival → month M (same as sale month)

        Inflow timing:
          - Revenue receipt: compute_receipt_date(invoice_date=period_start) per
            customer's forecast.customer.term rule; buckets to the receipt month.

        If no supplier terms are configured, falls back to:
          deposit 3 months back, balance 1 month back (sensible NZ import defaults).
        If no customer terms are found for a partner, falls back to 45 days + 20th DOM.
        """
        CashflowLine = self.env['forecast.cashflow.line']
        CustomerTerm = self.env['forecast.customer.term']

        # Build month index for bucketing inflows/outflows
        month_map = {m[0]: m[1] for m in months}
        month_set = set(month_map.keys())

        # --- Resolve supplier payment timing parameters ---
        supplier_terms = config.supplier_term_ids
        if supplier_terms:
            # Use the first configured supplier term.
            # Future: loop over terms if supplier_id is on cogs lines.
            s_term = supplier_terms[0]
            deposit_months_back = math.ceil(s_term.deposit_trigger_days / 30.0)
            transit_months_back = math.ceil(s_term.transit_days / 30.0)
            deposit_pct = s_term.deposit_pct / 100.0
        else:
            # Default NZ import assumptions: ~90-day total lead → 3-month deposit,
            # ~22-day transit → 1-month balance.
            deposit_months_back = 3
            transit_months_back = 1
            deposit_pct = 0.30

        balance_pct = 1.0 - deposit_pct

        # GST/import tax rate: prefer config.tax_id, fallback to NZ 15%
        tax_rate = config.tax_id.amount / 100.0 if config.tax_id else 0.15

        # --- Initialise accumulators per month ---
        # Payables (split by type for auditable P&L mapping)
        fob_deposit_by_month = defaultdict(float)
        fob_balance_by_month = defaultdict(float)
        freight_by_month = defaultdict(float)
        duty_gst_by_month = defaultdict(float)
        tpl_by_month = defaultdict(float)

        for cogs in cogs_lines:
            sale_month = cogs.period_start
            if sale_month not in month_set:
                continue

            fob = cogs.fob_total_nzd
            freight = cogs.freight_total_nzd
            duty = cogs.duty_total_nzd

            # Deposit payment: ceil(deposit_trigger_days/30) months before sale
            deposit_month = (
                sale_month - relativedelta(months=deposit_months_back)
            ).replace(day=1)
            if deposit_month in month_set:
                fob_deposit_by_month[deposit_month] += fob * deposit_pct

            # Balance payment: ceil(transit_days/30) months before sale
            balance_month = (
                sale_month - relativedelta(months=transit_months_back)
            ).replace(day=1)
            if balance_month in month_set:
                fob_balance_by_month[balance_month] += fob * balance_pct
                # Freight paid same month as balance (forwarder invoices at shipment)
                freight_by_month[balance_month] += freight

            # GST/duty: paid on arrival, which aligns with the sale month
            # CIF = FOB + freight; GST is levied on CIF value.
            cif = fob + freight
            gst_on_import = cif * tax_rate
            if sale_month in month_set:
                duty_gst_by_month[sale_month] += duty + gst_on_import

            # 3PL: pick/pack/despatch costs incurred in the sale month
            if sale_month in month_set:
                tpl_by_month[sale_month] += cogs.tpl_total_nzd

        # --- Receivables: bucket revenue by customer receipt month ---
        receipts_by_month = defaultdict(float)
        for rev in revenue_lines:
            invoice_date = rev.period_start  # treat 1st of month as invoice date
            receipt_date = CustomerTerm.get_default_receipt_date(
                config, rev.partner_id.id, invoice_date,
            )
            receipt_month = receipt_date.replace(day=1)
            if receipt_month in month_set:
                receipts_by_month[receipt_month] += rev.revenue

        # --- OpEx cash outflows (fixed: same month; variable: proportional to revenue) ---
        opex_fixed_monthly = sum(
            line.monthly_amount or 0.0
            for line in config.opex_line_ids
            if line.cost_type == 'fixed'
        )

        # --- Build cashflow lines ---
        lines_data = []
        for period_start, period_label in months:
            # Variable opex for this month
            month_rev = sum(
                r.revenue for r in revenue_lines
                if r.period_start == period_start
            )
            opex_var = sum(
                month_rev * (line.pct_of_revenue / 100.0)
                for line in config.opex_line_ids
                if line.cost_type == 'variable'
            )

            # Aggregate FOB deposit + balance into payments_fob
            payments_fob = (
                fob_deposit_by_month.get(period_start, 0.0)
                + fob_balance_by_month.get(period_start, 0.0)
            )

            lines_data.append({
                'config_id': config.id,
                'period_start': period_start,
                'period_label': period_label,
                'receipts_from_customers': receipts_by_month.get(period_start, 0.0),
                'payments_fob': payments_fob,
                'payments_freight': freight_by_month.get(period_start, 0.0),
                'payments_duty_gst': duty_gst_by_month.get(period_start, 0.0),
                'payments_3pl': tpl_by_month.get(period_start, 0.0),
                'payments_opex': opex_fixed_monthly + opex_var,
            })

        lines = CashflowLine.create(lines_data)

        # Compute cumulative cash position (running total over sorted periods)
        cumulative = 0.0
        for line in lines.sorted('period_start'):
            cumulative += line.net_cashflow
            line.cumulative_cashflow = cumulative

        _logger.info(
            'Created %d cash flow lines (deposit %d months back, balance %d months back)',
            len(lines), deposit_months_back, transit_months_back,
        )
        return lines
