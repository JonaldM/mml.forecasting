"""
run_forecast_e2e.py — End-to-end MML Financial Forecast

Runs the full forecast pipeline in pure Python (no Odoo) against a representative
MML Consumer Products scenario, then runs an independent hand-calculation over the
same inputs, compares the two, and writes an HTML report.

Usage:
    python scripts/run_forecast_e2e.py
    # writes: scripts/forecast_report.html
"""
import math
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Scenario definition — representative MML Consumer Products inputs
# ---------------------------------------------------------------------------

SCENARIO = {
    'name': 'MML Consumer Products — FY2026 Financial Forecast',
    'date_start': date(2026, 4, 1),
    'horizon_months': 12,

    # FX: convention = "NZD buys X FCY" so USD=0.60 → 1 NZD = 0.60 USD
    # fx_rate_applied (NZD per FCY) = 1 / rate_to_nzd
    'fx_usd_to_nzd': 1 / 0.60,   # 1.6667 NZD per USD

    'freight_rate_cbm': 200.0,     # NZD per CBM (LCL China-NZ)
    'gst_rate': 0.15,              # NZ GST 15%

    # Supplier terms — 100% TT at NZ port arrival (actual practice, not B/L date)
    # Contractual terms are "100% TT on B/L" but payment is made when the vessel
    # arrives at NZ port (~25-30 day transit from China). Goods available for sale
    # after customs clearance + 3PL delivery, which falls within the same calendar
    # month as port arrival. Modelled as: 0% deposit, 100% in sale month (months_back=0).
    'deposit_pct': 0.0,
    'deposit_months_back': 0,      # no deposit
    'balance_months_back': 0,      # 100% at port arrival = same month as sale

    # Customer terms: 45 days from invoice date, then next 20th of month
    'customer_payment_days': 45,
    'customer_payment_dom': 20,    # day-of-month for settlement

    # Opening balances (from trial balance at 2026-04-01)
    'opening_cash': 500_000.0,
    'opening_inventory': 800_000.0,
    'opening_receivables': 0.0,
    'opening_payables': 350_000.0,
    'opening_equity': 1_200_000.0,

    # OpEx (fixed only for simplicity)
    'opex_fixed_monthly': 50_000.0,

    # Products: units_per_month scaled to ~$3.8M ex-GST annual revenue
    # (actual FY run-rate per management; previous scenario was ~$1.8M — corrected)
    'products': [
        {
            'code': 'VOLERE-001', 'brand': 'Volere', 'category': 'Cleaning',
            'fob_usd': 8.50,  'cbm': 0.004, 'tariff_pct': 0.0, 'tpl_rate': 2.50,
            'units_per_month': 1_050, 'sell_price_nzd': 42.50,
        },
        {
            'code': 'VOLERE-002', 'brand': 'Volere', 'category': 'Cleaning',
            'fob_usd': 12.00, 'cbm': 0.006, 'tariff_pct': 0.0, 'tpl_rate': 2.50,
            'units_per_month': 630, 'sell_price_nzd': 60.00,
        },
        {
            'code': 'AL-001', 'brand': 'Annabel Langbein', 'category': 'Kitchenware',
            'fob_usd': 15.00, 'cbm': 0.008, 'tariff_pct': 0.0, 'tpl_rate': 3.00,
            'units_per_month': 840, 'sell_price_nzd': 75.00,
        },
        {
            'code': 'AL-002', 'brand': 'Annabel Langbein', 'category': 'Kitchenware',
            'fob_usd': 22.00, 'cbm': 0.010, 'tariff_pct': 5.0, 'tpl_rate': 3.00,
            'units_per_month': 525, 'sell_price_nzd': 110.00,
        },
        {
            'code': 'ENKEL-001', 'brand': 'Enkel', 'category': 'Storage',
            'fob_usd': 6.00,  'cbm': 0.003, 'tariff_pct': 0.0, 'tpl_rate': 2.00,
            'units_per_month': 1_260, 'sell_price_nzd': 30.00,
        },
        {
            'code': 'ENDURO-001', 'brand': 'Enduro', 'category': 'Outdoors',
            'fob_usd': 18.00, 'cbm': 0.012, 'tariff_pct': 0.0, 'tpl_rate': 3.50,
            'units_per_month': 420, 'sell_price_nzd': 90.00,
        },
        {
            'code': 'RC-001', 'brand': 'Rufus & Coco', 'category': 'Pet',
            'fob_usd': 10.00, 'cbm': 0.005, 'tariff_pct': 0.0, 'tpl_rate': 2.50,
            'units_per_month': 740, 'sell_price_nzd': 50.00,
        },
    ],
}


# ---------------------------------------------------------------------------
# PIPELINE — mirrors forecast_generate_wizard.py exactly
# ---------------------------------------------------------------------------

def build_month_buckets(date_start, horizon_months):
    months = []
    current = date_start.replace(day=1)
    for _ in range(horizon_months):
        months.append((current, current.strftime('%Y-%m')))
        current += relativedelta(months=1)
    return months


def compute_cogs_line(product, units, fx_usd_to_nzd, freight_rate_cbm):
    """Mirror ForecastCogsLine._compute_totals()"""
    fob_unit_nzd = product['fob_usd'] * fx_usd_to_nzd
    freight_unit_nzd = product['cbm'] * freight_rate_cbm
    cif_unit_nzd = fob_unit_nzd + freight_unit_nzd
    duty_unit_nzd = cif_unit_nzd * (product['tariff_pct'] / 100.0)
    tpl_unit_nzd = product['tpl_rate']
    landed_unit_nzd = fob_unit_nzd + freight_unit_nzd + duty_unit_nzd + tpl_unit_nzd
    return {
        'fob_unit_nzd': fob_unit_nzd,
        'fob_total_nzd': fob_unit_nzd * units,
        'freight_unit_nzd': freight_unit_nzd,
        'freight_total_nzd': freight_unit_nzd * units,
        'cif_unit_nzd': cif_unit_nzd,
        'duty_unit_nzd': duty_unit_nzd,
        'duty_total_nzd': duty_unit_nzd * units,
        'tpl_total_nzd': tpl_unit_nzd * units,
        'landed_unit_nzd': landed_unit_nzd,
        'total_cogs_nzd': landed_unit_nzd * units,
    }


def compute_customer_receipt_month(sale_month, payment_days, payment_dom):
    """Mirror ForecastCustomerTerm.compute_receipt_date() — days_then_dom rule."""
    invoice_date = sale_month
    raw_date = invoice_date + relativedelta(days=payment_days)
    if raw_date.day <= payment_dom:
        receipt_date = raw_date.replace(day=payment_dom)
    else:
        receipt_date = (raw_date + relativedelta(months=1)).replace(day=payment_dom)
    return receipt_date.replace(day=1)


def run_pipeline(scenario):
    """
    Full generation pipeline — pure Python mirror of ForecastGenerateWizard.generate().
    Returns dict with all line-level results keyed by period_label.
    """
    s = scenario
    months = build_month_buckets(s['date_start'], s['horizon_months'])
    month_dates = {m[0] for m in months}
    products = s['products']

    # ------------------------------------------------------------------ #
    # 1. Revenue lines (per product per month)                            #
    # ------------------------------------------------------------------ #
    revenue_lines = []
    for product in products:
        for period_start, period_label in months:
            units = product['units_per_month']
            sell = product['sell_price_nzd']
            receipt_month = compute_customer_receipt_month(
                period_start, s['customer_payment_days'], s['customer_payment_dom']
            )
            revenue_lines.append({
                'product': product['code'],
                'brand': product['brand'],
                'period_start': period_start,
                'period_label': period_label,
                'units': units,
                'sell_price': sell,
                'revenue': units * sell,
                'receipt_month': receipt_month,
            })

    # ------------------------------------------------------------------ #
    # 2. COGS lines (per product per month)                               #
    # ------------------------------------------------------------------ #
    cogs_lines = []
    for product in products:
        cog = compute_cogs_line(product, product['units_per_month'],
                                s['fx_usd_to_nzd'], s['freight_rate_cbm'])
        for period_start, period_label in months:
            cogs_lines.append({
                'product': product['code'],
                'brand': product['brand'],
                'period_start': period_start,
                'period_label': period_label,
                'units': product['units_per_month'],
                **cog,
            })

    # ------------------------------------------------------------------ #
    # 3. P&L lines (monthly aggregate)                                    #
    # ------------------------------------------------------------------ #
    pnl_lines = []
    for period_start, period_label in months:
        month_rev = [r for r in revenue_lines if r['period_start'] == period_start]
        month_cogs = [c for c in cogs_lines if c['period_start'] == period_start]
        total_revenue = sum(r['revenue'] for r in month_rev)
        cogs_fob = sum(c['fob_total_nzd'] for c in month_cogs)
        cogs_freight = sum(c['freight_total_nzd'] for c in month_cogs)
        cogs_duty = sum(c['duty_total_nzd'] for c in month_cogs)
        cogs_3pl = sum(c['tpl_total_nzd'] for c in month_cogs)
        total_cogs = cogs_fob + cogs_freight + cogs_duty + cogs_3pl
        gross_margin = total_revenue - total_cogs
        gm_pct = (gross_margin / total_revenue * 100) if total_revenue else 0.0
        opex_fixed = s['opex_fixed_monthly']
        ebitda = gross_margin - opex_fixed
        ebitda_pct = (ebitda / total_revenue * 100) if total_revenue else 0.0
        pnl_lines.append({
            'period_start': period_start,
            'period_label': period_label,
            'revenue': total_revenue,
            'cogs_fob': cogs_fob,
            'cogs_freight': cogs_freight,
            'cogs_duty': cogs_duty,
            'cogs_3pl': cogs_3pl,
            'total_cogs': total_cogs,
            'gross_margin': gross_margin,
            'gm_pct': gm_pct,
            'opex_fixed': opex_fixed,
            'ebitda': ebitda,
            'ebitda_pct': ebitda_pct,
        })

    # ------------------------------------------------------------------ #
    # 4. Cashflow lines (supplier timing + customer receipts)             #
    # ------------------------------------------------------------------ #
    # Mirror _generate_cashflow_lines() exactly
    dep_pct = s['deposit_pct']
    bal_pct = 1.0 - dep_pct
    dep_months_back = s['deposit_months_back']
    bal_months_back = s['balance_months_back']
    gst_rate = s['gst_rate']

    fob_deposit_by_month = defaultdict(float)
    fob_balance_by_month = defaultdict(float)
    freight_by_month = defaultdict(float)
    duty_gst_by_month = defaultdict(float)
    tpl_by_month = defaultdict(float)
    gst_refund_by_month = defaultdict(float)

    for cog in cogs_lines:
        sale_month = cog['period_start']
        fob = cog['fob_total_nzd']
        freight = cog['freight_total_nzd']
        duty = cog['duty_total_nzd']
        cif = cog['fob_total_nzd'] + cog['freight_total_nzd']
        gst_on_import = cif * gst_rate

        deposit_month = (sale_month - relativedelta(months=dep_months_back)).replace(day=1)
        balance_month = (sale_month - relativedelta(months=bal_months_back)).replace(day=1)
        refund_month = (sale_month + relativedelta(months=2)).replace(day=1)

        if deposit_month in month_dates:
            fob_deposit_by_month[deposit_month] += fob * dep_pct
        if balance_month in month_dates:
            fob_balance_by_month[balance_month] += fob * bal_pct
            freight_by_month[balance_month] += freight
        if sale_month in month_dates:
            duty_gst_by_month[sale_month] += duty + gst_on_import
            tpl_by_month[sale_month] += cog['tpl_total_nzd']
        if refund_month in month_dates:
            gst_refund_by_month[refund_month] += gst_on_import

    # Customer receipts: bucket revenue by receipt_month
    receipts_by_month = defaultdict(float)
    for rev in revenue_lines:
        rm = rev['receipt_month']
        if rm in month_dates:
            receipts_by_month[rm] += rev['revenue']

    # Build cashflow lines and compute cumulative
    opex_monthly = s['opex_fixed_monthly']
    cashflow_lines = []
    for period_start, period_label in months:
        inflow = receipts_by_month.get(period_start, 0.0)
        gst_refund = gst_refund_by_month.get(period_start, 0.0)
        total_inflows = inflow + gst_refund
        fob_dep = fob_deposit_by_month.get(period_start, 0.0)
        fob_bal = fob_balance_by_month.get(period_start, 0.0)
        freight_out = freight_by_month.get(period_start, 0.0)
        duty_gst_out = duty_gst_by_month.get(period_start, 0.0)
        tpl_out = tpl_by_month.get(period_start, 0.0)
        total_outflows = fob_dep + fob_bal + freight_out + duty_gst_out + tpl_out + opex_monthly
        net = total_inflows - total_outflows
        cashflow_lines.append({
            'period_start': period_start,
            'period_label': period_label,
            'receipts_from_customers': inflow,
            'import_gst_refund': gst_refund,
            'total_inflows': total_inflows,
            'payments_fob_deposit': fob_dep,
            'payments_fob_balance': fob_bal,
            'payments_freight': freight_out,
            'payments_duty_gst': duty_gst_out,
            'payments_3pl': tpl_out,
            'payments_opex': opex_monthly,
            'total_outflows': total_outflows,
            'net_cashflow': net,
            'cumulative_cashflow': 0.0,  # set next
        })

    cumulative = 0.0
    for cf in cashflow_lines:
        cumulative += cf['net_cashflow']
        cf['cumulative_cashflow'] = cumulative

    # ------------------------------------------------------------------ #
    # 5. Balance sheet lines                                              #
    # ------------------------------------------------------------------ #
    opening_cash = s['opening_cash']
    opening_payables = s['opening_payables']
    first_period = months[0][0]
    inventory = s['opening_inventory']
    cumulative_ebitda = 0.0

    cf_by_month = {cf['period_start']: cf for cf in cashflow_lines}
    pnl_by_month = {p['period_start']: p for p in pnl_lines}

    # Future FOB balance after each month (uncommitted forward FOB)
    future_fob = {}
    for m_start, _ in months:
        future_fob[m_start] = sum(
            cf['payments_fob_balance']
            for cf in cashflow_lines
            if cf['period_start'] > m_start
        )

    bs_lines = []
    for period_start, period_label in months:
        cf = cf_by_month.get(period_start, {})
        pnl = pnl_by_month.get(period_start, {})
        cash = opening_cash + cf.get('cumulative_cashflow', 0.0)

        # Trade receivables: revenue lines where receipt_month > this month
        trade_rec = sum(
            r['revenue'] for r in revenue_lines
            if r['period_start'] <= period_start
            and r['receipt_month']
            and r['receipt_month'] > period_start
        )

        # Inventory roll-forward: FOB arrivals minus FOB-basis COGS
        fob_received = cf.get('payments_fob_balance', 0.0)
        fob_cogs = pnl.get('cogs_fob', 0.0)
        inventory += fob_received - fob_cogs

        # Trade payables
        trade_pay = future_fob.get(period_start, 0.0)
        if period_start == first_period:
            trade_pay += opening_payables

        # Retained earnings
        cumulative_ebitda += pnl.get('ebitda', 0.0)
        retained = s['opening_equity'] + cumulative_ebitda

        bs_lines.append({
            'period_start': period_start,
            'period_label': period_label,
            'cash': cash,
            'trade_receivables': trade_rec,
            'inventory_value': inventory,
            'trade_payables': trade_pay,
            'retained_earnings': retained,
        })

    # ------------------------------------------------------------------ #
    # 6. KPIs                                                             #
    # ------------------------------------------------------------------ #
    kpi_revenue = sum(p['revenue'] for p in pnl_lines)
    kpi_ebitda = sum(p['ebitda'] for p in pnl_lines)
    kpi_total_cogs = sum(p['total_cogs'] for p in pnl_lines)
    last_cf = cashflow_lines[-1]
    min_cf = min(cashflow_lines, key=lambda c: c['cumulative_cashflow'])
    kpi_ending_cash = opening_cash + last_cf['cumulative_cashflow']
    kpi_cash_low = opening_cash + min_cf['cumulative_cashflow']
    kpi_cash_low_month = min_cf['period_label']

    return {
        'revenue_lines': revenue_lines,
        'cogs_lines': cogs_lines,
        'pnl_lines': pnl_lines,
        'cashflow_lines': cashflow_lines,
        'bs_lines': bs_lines,
        'kpis': {
            'total_revenue': kpi_revenue,
            'total_ebitda': kpi_ebitda,
            'ebitda_margin_pct': (kpi_ebitda / kpi_revenue * 100) if kpi_revenue else 0.0,
            'total_cogs': kpi_total_cogs,
            'ending_cash': kpi_ending_cash,
            'cash_low_value': kpi_cash_low,
            'cash_low_month': kpi_cash_low_month,
        },
    }


# ---------------------------------------------------------------------------
# INDEPENDENT VERIFIER — hand-calculate expected figures for Month 1 & totals
# ---------------------------------------------------------------------------

def independent_verify(scenario):
    """
    Independently compute Month 1 and 12-month totals using direct arithmetic.
    No shared code with run_pipeline(). Used to cross-check the pipeline output.
    """
    s = scenario
    products = s['products']
    fx = s['fx_usd_to_nzd']
    fr = s['freight_rate_cbm']
    gst = s['gst_rate']
    dep_pct = s['deposit_pct']
    bal_pct = 1.0 - dep_pct

    # Per-product per-unit figures
    per_unit = []
    for p in products:
        fob_nzd = p['fob_usd'] * fx
        freight_nzd = p['cbm'] * fr
        cif_nzd = fob_nzd + freight_nzd
        duty_nzd = cif_nzd * (p['tariff_pct'] / 100.0)
        tpl_nzd = p['tpl_rate']
        landed_nzd = fob_nzd + freight_nzd + duty_nzd + tpl_nzd
        per_unit.append({
            'code': p['code'],
            'units': p['units_per_month'],
            'sell': p['sell_price_nzd'],
            'fob_nzd': fob_nzd,
            'freight_nzd': freight_nzd,
            'cif_nzd': cif_nzd,
            'duty_nzd': duty_nzd,
            'tpl_nzd': tpl_nzd,
            'landed_nzd': landed_nzd,
            'gst_import_unit': cif_nzd * gst,
        })

    # Month 1 revenue
    m1_revenue = sum(p['units'] * p['sell'] for p in per_unit)

    # Month 1 COGS
    m1_fob = sum(p['units'] * p['fob_nzd'] for p in per_unit)
    m1_freight = sum(p['units'] * p['freight_nzd'] for p in per_unit)
    m1_duty = sum(p['units'] * p['duty_nzd'] for p in per_unit)
    m1_3pl = sum(p['units'] * p['tpl_nzd'] for p in per_unit)
    m1_total_cogs = m1_fob + m1_freight + m1_duty + m1_3pl
    m1_gross_margin = m1_revenue - m1_total_cogs
    m1_gm_pct = m1_gross_margin / m1_revenue * 100
    m1_ebitda = m1_gross_margin - s['opex_fixed_monthly']

    # Monthly GST on import
    m1_gst_import = sum(p['units'] * p['gst_import_unit'] for p in per_unit)

    # Month 1 cashflow
    # Payment terms: 100% TT at port arrival = 0% deposit, 100% in same month as sale.
    # Goods arrive at NZ port in the same calendar month they are sold (25-30 day transit).
    # So ALL supplier outflows (FOB 100%, freight) land in the sale month.
    # Customer receipts: M1 revenue received in M2 (45 days + 20th DOM → May 2026).
    # GST refund: M1 payment refunded in M3 (2-month lag).
    m1_cf_inflow = 0.0           # no customer receipts in M1 (all shift to M2+)
    m1_gst_refund = 0.0          # GST refund for M1 lands in M3
    m1_fob_deposit = 0.0                        # no deposit under 100% TT at port
    m1_fob_balance = m1_fob * bal_pct           # 100% FOB paid in M1 (same month as sale)
    m1_freight_out = m1_freight                  # freight paid at port arrival = M1
    m1_duty_gst_out = m1_duty + m1_gst_import   # M1's own duty + GST at customs
    m1_3pl_out = m1_3pl
    m1_opex_out = s['opex_fixed_monthly']
    m1_total_out = (m1_fob_deposit + m1_fob_balance + m1_freight_out
                    + m1_duty_gst_out + m1_3pl_out + m1_opex_out)
    m1_net_cf = m1_cf_inflow - m1_total_out
    m1_ending_cash = s['opening_cash'] + m1_net_cf   # cumulative after M1

    # 12-month KPIs (flat demand, 100% TT at port — all months identical except M1)
    # Revenue: 12 × m1_revenue
    total_12_revenue = m1_revenue * 12

    # COGS: 12 × m1 (flat demand)
    total_12_cogs = m1_total_cogs * 12
    total_12_ebitda = m1_ebitda * 12

    # Ending cash (12-month direct calculation):
    # Inflows: customer receipts for M2-M12 = 11 × m1_revenue
    #          GST refunds for M3-M12 = 10 × m1_gst_import
    # Outflows: FOB 100% all 12 months = 12 × m1_fob
    #           freight all 12 months = 12 × m1_freight
    #           duty+GST all 12 months = 12 × (m1_duty + m1_gst_import)
    #           3PL all 12 months = 12 × m1_3pl
    #           OpEx all 12 months = 12 × opex
    total_inflows = (m1_revenue * 11) + (m1_gst_import * 10)
    total_outflows = (
        m1_fob * 12               # 100% FOB in same month, all 12 months
        + m1_freight * 12
        + (m1_duty + m1_gst_import) * 12
        + m1_3pl * 12
        + s['opex_fixed_monthly'] * 12
    )
    total_12_net_cf = total_inflows - total_outflows
    ending_cash_12 = s['opening_cash'] + total_12_net_cf

    return {
        'month1': {
            'revenue': m1_revenue,
            'cogs_fob': m1_fob,
            'cogs_freight': m1_freight,
            'cogs_duty': m1_duty,
            'cogs_3pl': m1_3pl,
            'total_cogs': m1_total_cogs,
            'gross_margin': m1_gross_margin,
            'gm_pct': m1_gm_pct,
            'ebitda': m1_ebitda,
            'gst_import': m1_gst_import,
            'cf_fob_deposit': m1_fob_deposit,
            'cf_fob_balance': m1_fob_balance,
            'cf_freight': m1_freight_out,
            'cf_duty_gst': m1_duty_gst_out,
            'cf_3pl': m1_3pl_out,
            'cf_opex': m1_opex_out,
            'cf_total_out': m1_total_out,
            'cf_net': m1_net_cf,
            'ending_cash_after_m1': m1_ending_cash,
        },
        'totals_12': {
            'revenue': total_12_revenue,
            'cogs': total_12_cogs,
            'ebitda': total_12_ebitda,
            'ending_cash': ending_cash_12,
        },
    }


# ---------------------------------------------------------------------------
# Comparison helper
# ---------------------------------------------------------------------------

def compare(pipeline_result, verifier_result, tol=0.02):
    """
    Compare pipeline output vs independent verifier.
    Returns list of {field, pipeline, verifier, diff, pct_diff, pass}.
    tol: relative tolerance (2% default).
    """
    results = []

    def check(label, pipe_val, ver_val):
        diff = pipe_val - ver_val
        pct = abs(diff / ver_val * 100) if ver_val else (0.0 if diff == 0 else float('inf'))
        results.append({
            'label': label,
            'pipeline': pipe_val,
            'verifier': ver_val,
            'diff': diff,
            'pct_diff': pct,
            'pass': pct <= tol * 100,
        })

    pnl_m1 = pipeline_result['pnl_lines'][0]
    cf_m1 = pipeline_result['cashflow_lines'][0]
    ver_m1 = verifier_result['month1']
    ver_12 = verifier_result['totals_12']
    kpis = pipeline_result['kpis']

    # Month 1 P&L
    check('M1 Revenue', pnl_m1['revenue'], ver_m1['revenue'])
    check('M1 FOB COGS', pnl_m1['cogs_fob'], ver_m1['cogs_fob'])
    check('M1 Freight COGS', pnl_m1['cogs_freight'], ver_m1['cogs_freight'])
    check('M1 Duty COGS', pnl_m1['cogs_duty'], ver_m1['cogs_duty'])
    check('M1 3PL COGS', pnl_m1['cogs_3pl'], ver_m1['cogs_3pl'])
    check('M1 Total COGS', pnl_m1['total_cogs'], ver_m1['total_cogs'])
    check('M1 Gross Margin', pnl_m1['gross_margin'], ver_m1['gross_margin'])
    check('M1 EBITDA', pnl_m1['ebitda'], ver_m1['ebitda'])

    # Month 1 cashflow
    check('M1 FOB Deposit Out', cf_m1['payments_fob_deposit'], ver_m1['cf_fob_deposit'])
    check('M1 FOB Balance Out', cf_m1['payments_fob_balance'], ver_m1['cf_fob_balance'])
    check('M1 Freight Out', cf_m1['payments_freight'], ver_m1['cf_freight'])
    check('M1 Duty+GST Out', cf_m1['payments_duty_gst'], ver_m1['cf_duty_gst'])
    check('M1 Net Cashflow', cf_m1['net_cashflow'], ver_m1['cf_net'])

    # 12-month KPIs
    check('12M Revenue', kpis['total_revenue'], ver_12['revenue'])
    check('12M Total COGS', kpis['total_cogs'], ver_12['cogs'])
    check('12M EBITDA', kpis['total_ebitda'], ver_12['ebitda'])
    check('12M Ending Cash', kpis['ending_cash'], ver_12['ending_cash'])

    return results


# ---------------------------------------------------------------------------
# HTML Report generator
# ---------------------------------------------------------------------------

def nzd(v):
    return f'${v:,.2f}'


def pct(v):
    return f'{v:.2f}%'


def delta_class(v):
    return 'positive' if v > 0 else 'negative' if v < 0 else 'neutral'


REPORT_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f8f9fa;
       color: #212529; font-size: 14px; }
.page { max-width: 1200px; margin: 0 auto; padding: 24px; }
h1 { font-size: 22px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
.subtitle { color: #6c757d; font-size: 13px; margin-bottom: 28px; }
h2 { font-size: 15px; font-weight: 600; color: #343a40; margin: 28px 0 12px;
     padding-bottom: 6px; border-bottom: 2px solid #dee2e6; }
h3 { font-size: 13px; font-weight: 600; color: #495057; margin: 16px 0 8px; }

/* KPI cards */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
            margin-bottom: 28px; }
.kpi-card { background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
            padding: 16px 20px; }
.kpi-card .label { font-size: 11px; font-weight: 600; color: #6c757d;
                   text-transform: uppercase; letter-spacing: .5px; }
.kpi-card .value { font-size: 22px; font-weight: 700; color: #1a1a2e; margin-top: 4px; }
.kpi-card .sub { font-size: 11px; color: #6c757d; margin-top: 2px; }
.kpi-card.green { border-top: 3px solid #28a745; }
.kpi-card.blue { border-top: 3px solid #007bff; }
.kpi-card.amber { border-top: 3px solid #fd7e14; }
.kpi-card.red { border-top: 3px solid #dc3545; }

/* Tables */
table { width: 100%; border-collapse: collapse; background: #fff;
        border: 1px solid #dee2e6; border-radius: 8px; overflow: hidden;
        margin-bottom: 20px; font-size: 12.5px; }
thead th { background: #343a40; color: #fff; padding: 8px 10px;
           font-weight: 600; text-align: right; white-space: nowrap; }
thead th:first-child { text-align: left; }
tbody tr:nth-child(even) { background: #f8f9fa; }
tbody td { padding: 6px 10px; text-align: right; border-bottom: 1px solid #f1f3f5; }
tbody td:first-child { text-align: left; font-weight: 500; }
tfoot td { padding: 8px 10px; text-align: right; font-weight: 700;
           background: #e9ecef; border-top: 2px solid #adb5bd; }
tfoot td:first-child { text-align: left; }
.dim { color: #adb5bd; font-size: 11px; }
.pos { color: #28a745; }
.neg { color: #dc3545; }

/* Comparison table */
.cmp-pass { color: #28a745; font-weight: 600; }
.cmp-fail { color: #dc3545; font-weight: 600; }
.cmp-section { color: #6c757d; font-size: 11px; font-style: italic; }

/* Brand summary */
.brand-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;
              margin-bottom: 20px; }
.brand-card { background: #fff; border: 1px solid #dee2e6; border-radius: 6px;
              padding: 12px 14px; }
.brand-card .bname { font-weight: 700; font-size: 12px; color: #343a40;
                     margin-bottom: 6px; }
.brand-card .bval { font-size: 15px; font-weight: 600; }
.brand-card .bsub { font-size: 10px; color: #6c757d; }

/* Waterfall mini chart */
.waterfall { display: flex; align-items: flex-end; gap: 6px; height: 80px;
             margin-bottom: 16px; }
.wf-bar { flex: 1; border-radius: 3px 3px 0 0; position: relative; }
.wf-label { font-size: 9px; color: #6c757d; text-align: center; margin-top: 4px; }
"""


def render_html(scenario, pipeline, verifier, comparison):
    kpis = pipeline['kpis']
    pnl = pipeline['pnl_lines']
    cf = pipeline['cashflow_lines']
    bs = pipeline['bs_lines']

    # Brand revenue breakdown
    brand_revenue = defaultdict(float)
    for r in pipeline['revenue_lines']:
        brand_revenue[r['brand']] += r['revenue']

    def brand_cards():
        cards = []
        for brand, rev in sorted(brand_revenue.items()):
            pct_of_total = rev / kpis['total_revenue'] * 100
            cards.append(f"""
            <div class="brand-card">
              <div class="bname">{brand}</div>
              <div class="bval">{nzd(rev)}</div>
              <div class="bsub">{pct_of_total:.1f}% of total 12M revenue</div>
            </div>""")
        return '\n'.join(cards)

    def pnl_rows():
        rows = []
        for p in pnl:
            gm_cls = 'pos' if p['gross_margin'] > 0 else 'neg'
            eb_cls = 'pos' if p['ebitda'] > 0 else 'neg'
            rows.append(f"""
            <tr>
              <td>{p['period_label']}</td>
              <td>{nzd(p['revenue'])}</td>
              <td>{nzd(p['cogs_fob'])}</td>
              <td>{nzd(p['cogs_freight'])}</td>
              <td>{nzd(p['cogs_duty'])}</td>
              <td>{nzd(p['cogs_3pl'])}</td>
              <td>{nzd(p['total_cogs'])}</td>
              <td class="{gm_cls}">{nzd(p['gross_margin'])} <span class="dim">({p['gm_pct']:.1f}%)</span></td>
              <td>{nzd(p['opex_fixed'])}</td>
              <td class="{eb_cls}">{nzd(p['ebitda'])} <span class="dim">({p['ebitda_pct']:.1f}%)</span></td>
            </tr>""")
        tot_rev = sum(p['revenue'] for p in pnl)
        tot_cogs = sum(p['total_cogs'] for p in pnl)
        tot_gm = sum(p['gross_margin'] for p in pnl)
        tot_opex = sum(p['opex_fixed'] for p in pnl)
        tot_ebitda = sum(p['ebitda'] for p in pnl)
        rows.append(f"""
        <tfoot>
          <tr>
            <td>TOTAL 12M</td>
            <td>{nzd(tot_rev)}</td>
            <td colspan="4"></td>
            <td>{nzd(tot_cogs)}</td>
            <td>{nzd(tot_gm)} <span class="dim">({tot_gm/tot_rev*100:.1f}%)</span></td>
            <td>{nzd(tot_opex)}</td>
            <td>{nzd(tot_ebitda)} <span class="dim">({tot_ebitda/tot_rev*100:.1f}%)</span></td>
          </tr>
        </tfoot>""")
        return '\n'.join(rows)

    def cf_rows():
        rows = []
        for c in cf:
            net_cls = 'pos' if c['net_cashflow'] > 0 else 'neg'
            rows.append(f"""
            <tr>
              <td>{c['period_label']}</td>
              <td>{nzd(c['receipts_from_customers'])}</td>
              <td>{nzd(c['import_gst_refund'])}</td>
              <td>{nzd(c['payments_fob_deposit'])}</td>
              <td>{nzd(c['payments_fob_balance'])}</td>
              <td>{nzd(c['payments_freight'])}</td>
              <td>{nzd(c['payments_duty_gst'])}</td>
              <td>{nzd(c['payments_3pl'])}</td>
              <td>{nzd(c['payments_opex'])}</td>
              <td class="{net_cls}">{nzd(c['net_cashflow'])}</td>
              <td>{nzd(c['cumulative_cashflow'])}</td>
            </tr>""")
        return '\n'.join(rows)

    def bs_rows():
        rows = []
        for b in bs:
            rows.append(f"""
            <tr>
              <td>{b['period_label']}</td>
              <td>{nzd(b['cash'])}</td>
              <td>{nzd(b['trade_receivables'])}</td>
              <td>{nzd(b['inventory_value'])}</td>
              <td>{nzd(b['trade_payables'])}</td>
              <td>{nzd(b['retained_earnings'])}</td>
            </tr>""")
        return '\n'.join(rows)

    def cmp_rows():
        rows = []
        for c in comparison:
            status = '<span class="cmp-pass">PASS</span>' if c['pass'] else '<span class="cmp-fail">FAIL</span>'
            diff_cls = 'pos' if c['diff'] > 0 else 'neg' if c['diff'] < 0 else ''
            rows.append(f"""
            <tr>
              <td>{c['label']}</td>
              <td>{nzd(c['pipeline'])}</td>
              <td>{nzd(c['verifier'])}</td>
              <td class="{diff_cls}">{nzd(c['diff'])}</td>
              <td>{c['pct_diff']:.4f}%</td>
              <td>{status}</td>
            </tr>""")
        pass_count = sum(1 for c in comparison if c['pass'])
        rows.append(f"""
        <tfoot>
          <tr>
            <td colspan="5">Result: {pass_count}/{len(comparison)} checks passed</td>
            <td class="{'cmp-pass' if pass_count == len(comparison) else 'cmp-fail'}">
              {'ALL PASS' if pass_count == len(comparison) else f'{len(comparison)-pass_count} FAIL'}
            </td>
          </tr>
        </tfoot>""")
        return '\n'.join(rows)

    # COGS waterfall for month 1 (visual)
    m1_pnl = pnl[0]
    wf_items = [
        ('Revenue', m1_pnl['revenue'], '#007bff', 100),
        ('FOB', m1_pnl['cogs_fob'], '#fd7e14', m1_pnl['cogs_fob']/m1_pnl['revenue']*100),
        ('Freight', m1_pnl['cogs_freight'], '#ffc107', m1_pnl['cogs_freight']/m1_pnl['revenue']*100),
        ('Duty', m1_pnl['cogs_duty'], '#e83e8c', m1_pnl['cogs_duty']/m1_pnl['revenue']*100),
        ('3PL', m1_pnl['cogs_3pl'], '#6f42c1', m1_pnl['cogs_3pl']/m1_pnl['revenue']*100),
        ('EBITDA', m1_pnl['ebitda'], '#28a745', m1_pnl['ebitda']/m1_pnl['revenue']*100),
    ]

    wf_bars = ''.join(f"""
    <div style="text-align:center; flex:1">
      <div class="wf-bar" style="background:{color}; height:{min(h, 100):.1f}px;"></div>
      <div class="wf-label">{label}<br><span style="font-size:10px;font-weight:600">{val/m1_pnl['revenue']*100:.1f}%</span></div>
    </div>""" for label, val, color, h in wf_items)

    generated_at = date.today().isoformat()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MML Financial Forecast — E2E Report</title>
<style>{REPORT_CSS}</style>
</head>
<body>
<div class="page">

  <h1>MML Consumer Products — Financial Forecast</h1>
  <p class="subtitle">12-Month Forecast: Apr 2026 – Mar 2027 &nbsp;·&nbsp; Generated: {generated_at}
     &nbsp;·&nbsp; 7 SKUs across 5 brands &nbsp;·&nbsp; NZD</p>

  <!-- KPI Cards -->
  <div class="kpi-grid" id="kpi-section">
    <div class="kpi-card green">
      <div class="label">12M Revenue</div>
      <div class="value" id="kpi-revenue">{nzd(kpis['total_revenue'])}</div>
      <div class="sub">Flat demand scenario</div>
    </div>
    <div class="kpi-card blue">
      <div class="label">12M EBITDA</div>
      <div class="value" id="kpi-ebitda">{nzd(kpis['total_ebitda'])}</div>
      <div class="sub">{kpis['ebitda_margin_pct']:.1f}% margin</div>
    </div>
    <div class="kpi-card amber">
      <div class="label">Ending Cash (Mar 2027)</div>
      <div class="value" id="kpi-ending-cash">{nzd(kpis['ending_cash'])}</div>
      <div class="sub">Opening: {nzd(SCENARIO['opening_cash'])}</div>
    </div>
    <div class="kpi-card red">
      <div class="label">Cash Low Point</div>
      <div class="value" id="kpi-cash-low">{nzd(kpis['cash_low_value'])}</div>
      <div class="sub">Occurs in {kpis['cash_low_month']}</div>
    </div>
  </div>

  <!-- Brand breakdown -->
  <h2>Revenue by Brand (12M)</h2>
  <div class="brand-grid">{brand_cards()}</div>

  <!-- COGS Waterfall -->
  <h2>Month 1 (Apr 2026) — Cost Waterfall</h2>
  <div style="background:#fff; border:1px solid #dee2e6; border-radius:8px;
              padding:20px; margin-bottom:20px;">
    <h3>As % of Revenue &nbsp;<span style="color:#6c757d;font-weight:400;font-size:11px">
        Revenue: {nzd(m1_pnl['revenue'])} &nbsp;
        GM: {nzd(m1_pnl['gross_margin'])} ({m1_pnl['gm_pct']:.1f}%) &nbsp;
        EBITDA: {nzd(m1_pnl['ebitda'])} ({m1_pnl['ebitda_pct']:.1f}%)</span></h3>
    <div style="display:flex; align-items:flex-end; gap:8px; height:100px; margin-top:12px;">
      {wf_bars}
    </div>
  </div>

  <!-- P&L Table -->
  <h2>Profit &amp; Loss — Monthly Detail</h2>
  <table id="pnl-table">
    <thead>
      <tr>
        <th style="text-align:left">Period</th>
        <th>Revenue</th>
        <th>FOB</th>
        <th>Freight</th>
        <th>Duty</th>
        <th>3PL</th>
        <th>Total COGS</th>
        <th>Gross Margin</th>
        <th>OpEx</th>
        <th>EBITDA</th>
      </tr>
    </thead>
    <tbody>
      {pnl_rows()}
    </tbody>
  </table>

  <!-- Cashflow Table -->
  <h2>Cash Flow — Monthly Detail</h2>
  <p style="color:#6c757d;font-size:11px;margin-bottom:8px">
    Supplier: 30% deposit 3 months ahead · 70% balance 1 month ahead ·
    Customer: 45 days + 20th DOM · GST refund: 2-month lag
  </p>
  <table id="cf-table">
    <thead>
      <tr>
        <th style="text-align:left">Period</th>
        <th>Cust. Receipts</th>
        <th>GST Refund</th>
        <th>FOB Deposit</th>
        <th>FOB Balance</th>
        <th>Freight</th>
        <th>Duty+GST</th>
        <th>3PL</th>
        <th>OpEx</th>
        <th>Net CF</th>
        <th>Cumulative</th>
      </tr>
    </thead>
    <tbody>
      {cf_rows()}
    </tbody>
  </table>

  <!-- Balance Sheet -->
  <h2>Balance Sheet Snapshots</h2>
  <table id="bs-table">
    <thead>
      <tr>
        <th style="text-align:left">Period</th>
        <th>Cash</th>
        <th>Trade Receivables</th>
        <th>Inventory</th>
        <th>Trade Payables</th>
        <th>Retained Earnings</th>
      </tr>
    </thead>
    <tbody>
      {bs_rows()}
    </tbody>
  </table>

  <!-- Comparison / Verification -->
  <h2>Independent Verification — Pipeline vs Hand-Calculation</h2>
  <p style="color:#6c757d;font-size:11px;margin-bottom:8px">
    Tolerance: 2% relative difference. All figures NZD.
  </p>
  <table id="cmp-table">
    <thead>
      <tr>
        <th style="text-align:left">Check</th>
        <th>Pipeline</th>
        <th>Verifier</th>
        <th>Diff</th>
        <th>% Diff</th>
        <th>Result</th>
      </tr>
    </thead>
    <tbody>
      {cmp_rows()}
    </tbody>
  </table>

  <!-- Product inputs -->
  <h2>Scenario Inputs — Products</h2>
  <table>
    <thead>
      <tr>
        <th style="text-align:left">Code</th>
        <th style="text-align:left">Brand</th>
        <th>FOB (USD)</th>
        <th>FX Rate</th>
        <th>FOB (NZD)</th>
        <th>CBM/unit</th>
        <th>Freight/unit</th>
        <th>Tariff%</th>
        <th>Duty/unit</th>
        <th>3PL/unit</th>
        <th>Landed/unit</th>
        <th>Sell</th>
        <th>GM/unit</th>
        <th>Units/mo</th>
      </tr>
    </thead>
    <tbody>
"""

    fx = scenario['fx_usd_to_nzd']
    fr = scenario['freight_rate_cbm']
    for p in scenario['products']:
        fob_nzd = p['fob_usd'] * fx
        freight_u = p['cbm'] * fr
        cif_u = fob_nzd + freight_u
        duty_u = cif_u * (p['tariff_pct'] / 100.0)
        landed_u = fob_nzd + freight_u + duty_u + p['tpl_rate']
        gm_u = p['sell_price_nzd'] - landed_u
        html += f"""
      <tr>
        <td style="text-align:left">{p['code']}</td>
        <td style="text-align:left">{p['brand']}</td>
        <td>{p['fob_usd']:.2f}</td>
        <td>1/{1/fx:.2f}</td>
        <td>{fob_nzd:.4f}</td>
        <td>{p['cbm']:.3f}</td>
        <td>{freight_u:.2f}</td>
        <td>{p['tariff_pct']:.1f}</td>
        <td>{duty_u:.4f}</td>
        <td>{p['tpl_rate']:.2f}</td>
        <td>{landed_u:.4f}</td>
        <td>{p['sell_price_nzd']:.2f}</td>
        <td class="{'pos' if gm_u>0 else 'neg'}">{gm_u:.4f}</td>
        <td>{p['units_per_month']}</td>
      </tr>"""

    html += """
    </tbody>
  </table>
</div>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print('Running pipeline...')
    pipeline = run_pipeline(SCENARIO)

    print('Running independent verifier...')
    verifier = independent_verify(SCENARIO)

    print('Comparing results...')
    comparison = compare(pipeline, verifier)

    passes = sum(1 for c in comparison if c['pass'])
    print(f'\nComparison: {passes}/{len(comparison)} checks passed')

    # Print summary to stdout
    kpis = pipeline['kpis']
    print(f"\n{'='*60}")
    print(f"  12M Revenue:     {nzd(kpis['total_revenue'])}")
    print(f"  12M EBITDA:      {nzd(kpis['total_ebitda'])} ({kpis['ebitda_margin_pct']:.1f}%)")
    print(f"  12M Total COGS:  {nzd(kpis['total_cogs'])}")
    print(f"  Ending Cash:     {nzd(kpis['ending_cash'])}")
    print(f"  Cash Low Point:  {nzd(kpis['cash_low_value'])} ({kpis['cash_low_month']})")
    print(f"{'='*60}\n")

    for c in comparison:
        status = 'PASS' if c['pass'] else 'FAIL'
        print(f"  [{status}] {c['label']:<35} pipeline={nzd(c['pipeline'])}  "
              f"verifier={nzd(c['verifier'])}  diff={c['pct_diff']:.4f}%")

    html = render_html(SCENARIO, pipeline, verifier, comparison)
    out = Path(__file__).parent / 'forecast_report.html'
    out.write_text(html, encoding='utf-8')
    print(f'\nReport written: {out}')

    # Emit JSON for Playwright test to read
    json_out = Path(__file__).parent / 'forecast_data.json'
    json_out.write_text(json.dumps({
        'kpis': {k: round(v, 2) if isinstance(v, float) else v
                 for k, v in kpis.items()},
        'month1_pnl': {k: round(v, 2) if isinstance(v, float) else v
                       for k, v in pipeline['pnl_lines'][0].items()
                       if not isinstance(v, date)},
        'month1_cf': {k: round(v, 2) if isinstance(v, float) else v
                      for k, v in pipeline['cashflow_lines'][0].items()
                      if not isinstance(v, date)},
        'comparison_passed': passes == len(comparison),
        'passes': passes,
        'total_checks': len(comparison),
    }, indent=2, default=str), encoding='utf-8')

    return 0 if passes == len(comparison) else 1


if __name__ == '__main__':
    sys.exit(main())
