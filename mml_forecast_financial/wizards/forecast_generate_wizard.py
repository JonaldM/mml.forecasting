import logging
import math
from collections import defaultdict
from datetime import date

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
            3. Build revenue lines (with receipt_month per customer term)
            4. Build COGS waterfall lines (with supplier_id for timing)
            5. Aggregate to P&L summary
            6. Compute cash flow timing (per-supplier deposit/balance split)
            7. Build balance sheet snapshots
            8. Compute forecast vs actual variance for past periods
        """
        # Clear previous generated data
        config.revenue_line_ids.unlink()
        config.cogs_line_ids.unlink()
        config.pnl_line_ids.unlink()
        config.cashflow_line_ids.unlink()
        config.balance_sheet_line_ids.unlink()
        # Note: variance_line_ids are NOT unlinked here — _compute_variance_lines()
        # unlinks them internally so they are cleared correctly on both full
        # regeneration and standalone action_compute_variance() calls.

        months = self._build_month_buckets(config)
        demand = self._get_demand_forecast(config, months)

        if not demand:
            _logger.warning('No demand data found for forecast %s', config.name)
            return

        revenue_lines = self._generate_revenue_lines(config, demand)
        cogs_lines = self._generate_cogs_lines(config, demand)
        self._generate_pnl_lines(config, months, revenue_lines, cogs_lines)
        self._generate_cashflow_lines(config, months, revenue_lines, cogs_lines)
        self._generate_balance_sheet_lines(config, months)
        self._compute_variance_lines(config, months)

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

        # --- Strategy 1: ROQ module ---
        ForecastRun = self.env.get('roq.forecast.run')
        if ForecastRun is not None:
            runs = ForecastRun.search(
                [('status', '=', 'complete')], order='create_date desc', limit=1
            )
            if runs:
                try:
                    demand_data = runs.get_demand_forecast(
                        config.date_start, config.horizon_months
                    )
                except AttributeError:
                    _logger.warning(
                        'roq.forecast.run has no get_demand_forecast method; '
                        'falling back to sale history'
                    )
                    demand_data = []
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
        CustomerTerm = self.env['forecast.customer.term']
        lines_data = []

        for d in demand:
            product = self.env['product.product'].browse(d['product_id'])
            partner = self.env['res.partner'].browse(d['partner_id'])

            # Get sell price: try pricelist, fallback to list price
            sell_price = self._get_sell_price(product, partner)

            receipt_date = CustomerTerm.get_default_receipt_date(
                config, d['partner_id'], d['period_start'],
            )
            receipt_month = receipt_date.replace(day=1)

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
                'receipt_month': receipt_month,
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
                'supplier_id': supplier_info.get('partner_id', False),
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
                'partner_id': info.partner_id.id if info.partner_id else False,
            }
        return {'price': 0.0, 'currency': 'NZD', 'partner_id': False}

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

        # Build month index for bucketing inflows/outflows
        month_set = {m[0] for m in months}

        # --- Build per-supplier term lookup ---
        # Falls back to NZ import defaults when a product's supplier is not in the term list.
        _DEFAULT_DEPOSIT_MONTHS = 3
        _DEFAULT_TRANSIT_MONTHS = 1
        _DEFAULT_DEPOSIT_PCT = 0.30

        supplier_term_map = {
            term.supplier_id.id: term
            for term in config.supplier_term_ids
            if term.supplier_id
        }

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

            # Resolve per-supplier timing
            s_term = supplier_term_map.get(cogs.supplier_id.id if cogs.supplier_id else None)
            if s_term:
                deposit_months_back = math.ceil(s_term.deposit_trigger_days / 30.0)
                transit_months_back = math.ceil(s_term.transit_days / 30.0)
                deposit_pct = s_term.deposit_pct / 100.0
            else:
                deposit_months_back = _DEFAULT_DEPOSIT_MONTHS
                transit_months_back = _DEFAULT_TRANSIT_MONTHS
                deposit_pct = _DEFAULT_DEPOSIT_PCT
            balance_pct = 1.0 - deposit_pct

            # Deposit payment
            deposit_month = (
                sale_month - relativedelta(months=deposit_months_back)
            ).replace(day=1)
            if deposit_month in month_set:
                fob_deposit_by_month[deposit_month] += fob * deposit_pct

            # Balance payment
            balance_month = (
                sale_month - relativedelta(months=transit_months_back)
            ).replace(day=1)
            if balance_month in month_set:
                fob_balance_by_month[balance_month] += fob * balance_pct
                freight_by_month[balance_month] += freight

            # Duty + GST on arrival (sale month)
            cif = fob + freight
            gst_on_import = cif * tax_rate
            if sale_month in month_set:
                duty_gst_by_month[sale_month] += duty + gst_on_import

            # 3PL in sale month
            if sale_month in month_set:
                tpl_by_month[sale_month] += cogs.tpl_total_nzd

        # --- Receivables: bucket revenue by customer receipt month ---
        # receipt_month is populated on revenue lines during _generate_revenue_lines()
        receipts_by_month = defaultdict(float)
        for rev in revenue_lines:
            receipt_month = rev.receipt_month
            if receipt_month and receipt_month in month_set:
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

            lines_data.append({
                'config_id': config.id,
                'period_start': period_start,
                'period_label': period_label,
                'receipts_from_customers': receipts_by_month.get(period_start, 0.0),
                'payments_fob_deposit': fob_deposit_by_month.get(period_start, 0.0),
                'payments_fob_balance': fob_balance_by_month.get(period_start, 0.0),
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

        _logger.info('Created %d cash flow lines (per-supplier timing)', len(lines))
        return lines

    # -------------------------------------------------------------------------
    # Balance Sheet generation
    # -------------------------------------------------------------------------
    def _generate_balance_sheet_lines(self, config, months):
        """
        Build monthly balance sheet snapshots from opening balance + P&L + cashflow.

        Requires cumulative_cashflow to be set on all cashflow lines before calling.
        Calls flush_model() to ensure the DB is current.
        """
        self.env['forecast.cashflow.line'].flush_model()

        ob = config.opening_balance_ids[:1]
        if not ob:
            _logger.warning(
                'No opening balance on config %s — BS lines will use zero opening values',
                config.id,
            )

        inventory = ob.effective_inventory if ob else 0.0
        cumulative_ebitda = 0.0
        cashflow_by_month = {line.period_start: line for line in config.cashflow_line_ids}
        pnl_by_month = {line.period_start: line for line in config.pnl_line_ids}
        revenue_lines = config.revenue_line_ids

        # Pre-compute future FOB balance by month (for trade payables)
        # O(n^2) — acceptable at 12-24 month horizons.
        future_fob_balance = {
            m[0]: sum(
                line.payments_fob_balance
                for line in config.cashflow_line_ids
                if line.period_start > m[0]
            )
            for m in months
        }

        lines_data = []
        for period_start, period_label in months:
            cf = cashflow_by_month.get(period_start)
            pnl = pnl_by_month.get(period_start)

            cash = (ob.effective_cash if ob else 0.0) + (cf.cumulative_cashflow if cf else 0.0)

            trade_receivables = sum(
                r.revenue for r in revenue_lines
                if r.period_start <= period_start
                and r.receipt_month
                and r.receipt_month > period_start
            )

            # Inventory roll-forward (simplified):
            # - fob_received uses payment timing (balance month) as proxy for goods receipt
            #   (actual receipt is ~transit_days later; ignored here for planning-grade accuracy)
            # - total_cogs includes freight/duty/3PL, not only FOB cost of goods
            #   (full COGS used for simplicity; bs_difference absorbs this discrepancy)
            fob_received = cf.payments_fob_balance if cf else 0.0
            total_cogs = pnl.total_cogs if pnl else 0.0
            inventory += fob_received - total_cogs

            trade_payables = future_fob_balance.get(period_start, 0.0)
            cumulative_ebitda += pnl.ebitda if pnl else 0.0
            retained_earnings = (ob.effective_equity if ob else 0.0) + cumulative_ebitda

            lines_data.append({
                'config_id': config.id,
                'period_start': period_start,
                'period_label': period_label,
                'cash': cash,
                'trade_receivables': trade_receivables,
                'inventory_value': inventory,
                'trade_payables': trade_payables,
                'retained_earnings': retained_earnings,
            })

        lines = self.env['forecast.balance.sheet.line'].create(lines_data)
        _logger.info('Created %d balance sheet lines', len(lines))
        return lines

    # -------------------------------------------------------------------------
    # Variance computation
    # -------------------------------------------------------------------------
    def _compute_variance_lines(self, config, months):
        """
        Compute forecast vs actual variance for past periods.

        Pass 1: Product-level variance lines (forecast.variance.line).
        Pass 2: P&L summary actuals (actual_revenue, actual_cogs, actual_opex on forecast.pnl.line).

        Only processes months where period_start < date.today().
        Silently skips if all periods are in the future.
        """
        today = date.today()
        past_months = [(ps, pl) for ps, pl in months if ps < today]
        if not past_months:
            _logger.info('All forecast periods are in the future — skipping variance computation')
            return

        SaleOrderLine = self.env['sale.order.line']
        AccountMoveLine = self.env['account.move.line']
        VarianceLine = self.env['forecast.variance.line']

        # Unlink existing variance lines for this config before recomputing
        config.variance_line_ids.unlink()

        # --- Pass 1: Product-level variance ---
        for period_start, period_label in past_months:
            period_end = period_start + relativedelta(months=1)

            actual_sol = SaleOrderLine.search([
                # NOTE: no company_id filter — MML is single-company.
                # Add ('order_id.company_id', '=', config.company_id.id) if multi-entity is needed.
                ('order_id.state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', period_start),
                ('order_id.date_order', '<', period_end),
            ])

            # Group actuals by (product_id, partner_id)
            actual_by_key = defaultdict(lambda: {'units': 0.0, 'revenue': 0.0})
            for sol in actual_sol:
                key = (sol.product_id.id, sol.order_id.partner_id.id)
                actual_by_key[key]['units'] += sol.product_uom_qty
                actual_by_key[key]['revenue'] += sol.price_subtotal

            # Match against forecast revenue lines
            forecast_lines = config.revenue_line_ids.filtered(
                lambda r: r.period_start == period_start
            )

            lines_data = []
            for rev in forecast_lines:
                key = (rev.product_id.id, rev.partner_id.id)
                actuals = actual_by_key.get(key, {})
                lines_data.append({
                    'config_id': config.id,
                    'period_start': period_start,
                    'period_label': period_label,
                    'product_id': rev.product_id.id,
                    'partner_id': rev.partner_id.id,
                    'brand': rev.brand,
                    'category': rev.category,
                    'forecast_units': rev.forecast_units,
                    'forecast_revenue': rev.revenue,
                    'actual_units': actuals.get('units', 0.0),
                    'actual_revenue': actuals.get('revenue', 0.0),
                })

            if lines_data:
                VarianceLine.create(lines_data)

        # --- Pass 2: P&L summary actuals ---
        for pnl_line in config.pnl_line_ids.filtered(lambda l: l.period_start < today):
            period_end = pnl_line.period_start + relativedelta(months=1)

            aml = AccountMoveLine.search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', pnl_line.period_start),
                ('date', '<', period_end),
                ('company_id', '=', config.company_id.id),
            ])

            pnl_line.write({
                'actual_revenue': abs(sum(
                    line.balance for line in aml
                    if line.account_id.account_type in ('income', 'income_other')
                )),
                'actual_cogs': abs(sum(
                    line.balance for line in aml
                    if line.account_id.account_type == 'expense_direct_cost'
                )),
                'actual_opex': abs(sum(
                    line.balance for line in aml
                    if line.account_id.account_type == 'expense'
                )),
            })

        _logger.info(
            'Computed variance for %d past periods on config %s',
            len(past_months), config.id,
        )
