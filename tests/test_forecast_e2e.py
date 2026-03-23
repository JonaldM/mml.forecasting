"""
test_forecast_e2e.py — Playwright end-to-end test for MML Financial Forecast

Runs the standalone forecast pipeline (scripts/run_forecast_e2e.py), opens the
generated HTML report in a headless browser, validates key financial figures
against the expected pipeline output, and captures screenshots.

Run:
    pytest tests/test_forecast_e2e.py -v -s
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

SCRIPTS_DIR = Path(__file__).parent.parent / 'scripts'
REPORT_HTML = SCRIPTS_DIR / 'forecast_report.html'
REPORT_DATA = SCRIPTS_DIR / 'forecast_data.json'
SCREENSHOTS_DIR = Path(__file__).parent.parent / 'test-results' / 'e2e-screenshots'


# ---------------------------------------------------------------------------
# Session-scoped fixture: run the pipeline once and load the JSON output
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def pipeline_output():
    """Run forecast pipeline and return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / 'run_forecast_e2e.py')],
        capture_output=True, text=True,
    )
    print('\n--- Pipeline stdout ---')
    print(result.stdout)
    if result.returncode not in (0, 1):
        pytest.fail(f'Pipeline script error:\n{result.stderr}')
    assert REPORT_DATA.exists(), 'forecast_data.json not generated'
    return json.loads(REPORT_DATA.read_text())


@pytest.fixture(scope='session')
def report_url():
    """File URL for the generated HTML report."""
    assert REPORT_HTML.exists(), 'forecast_report.html not generated'
    return REPORT_HTML.as_uri()


@pytest.fixture(autouse=True)
def ensure_screenshots_dir():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def ss(page: Page, name: str):
    """Take a screenshot and save it."""
    path = SCREENSHOTS_DIR / f'{name}.png'
    page.screenshot(path=str(path), full_page=False)
    print(f'Screenshot: {path}')


def parse_nzd(text: str) -> float:
    """Convert '$1,234.56' → 1234.56"""
    return float(text.strip().replace('$', '').replace(',', ''))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestForecastPipelineVerification:
    """Verify the pipeline ran correctly and all comparison checks passed."""

    def test_pipeline_comparison_all_pass(self, pipeline_output):
        data = pipeline_output
        passed = data['passes']
        total = data['total_checks']
        assert data['comparison_passed'], (
            f'Independent verifier failed: {total - passed}/{total} checks did not match. '
            'Pipeline output diverges from hand-calculation.'
        )

    def test_revenue_reasonable(self, pipeline_output):
        rev = pipeline_output['kpis']['total_revenue']
        # 7 products × flat units × ~$150k/month × 12 months = ~$1.8M
        assert 1_600_000 < rev < 2_000_000, f'12M revenue {rev:,.0f} outside expected range'

    def test_ebitda_positive(self, pipeline_output):
        ebitda = pipeline_output['kpis']['total_ebitda']
        assert ebitda > 0, f'12M EBITDA {ebitda:,.0f} should be positive'

    def test_ebitda_margin_range(self, pipeline_output):
        rev = pipeline_output['kpis']['total_revenue']
        ebitda = pipeline_output['kpis']['total_ebitda']
        margin = ebitda / rev * 100
        # Given 60% gross margin and $50k/month opex, EBITDA margin ~26%
        assert 20.0 < margin < 35.0, f'EBITDA margin {margin:.1f}% outside expected 20-35% range'

    def test_ending_cash_higher_than_opening(self, pipeline_output):
        ending = pipeline_output['kpis']['ending_cash']
        opening = 500_000.0
        # Profitable business should finish with more cash than it started with
        assert ending > opening, f'Ending cash {ending:,.0f} < opening {opening:,.0f}'

    def test_cash_low_in_first_month(self, pipeline_output):
        # Month 1 has zero inflows but full outflows → cash dips before receipts start
        assert pipeline_output['kpis']['cash_low_month'] == '2026-04', (
            f'Expected cash low in 2026-04, got {pipeline_output["kpis"]["cash_low_month"]}'
        )

    def test_month1_gross_margin_pct(self, pipeline_output):
        m1 = pipeline_output['month1_pnl']
        gm_pct = m1['gross_margin'] / m1['revenue'] * 100
        # Expected ~59.8% (landed cost is ~40% of revenue)
        assert 55.0 < gm_pct < 65.0, f'Month 1 GM% {gm_pct:.1f}% outside 55-65% range'

    def test_month1_cashflow_is_negative(self, pipeline_output):
        cf = pipeline_output['month1_cf']
        assert cf['net_cashflow'] < 0, (
            'Month 1 net cashflow should be negative (paying for goods before receiving customers)'
        )

    def test_month1_zero_customer_receipts(self, pipeline_output):
        cf = pipeline_output['month1_cf']
        assert cf['receipts_from_customers'] == 0.0, (
            'Month 1 should have zero customer receipts (all receipts shifted to Month 2+)'
        )

    def test_duty_only_on_tariffed_products(self, pipeline_output):
        m1 = pipeline_output['month1_pnl']
        # Only AL-002 has 5% tariff. AL-002: 250 units
        # CIF/unit = (22/0.6 + 0.010*200) = 36.6667 + 2.00 = 38.6667
        # duty/unit = 38.6667 * 5% = 1.9333
        # total duty = 250 * 1.9333 = 483.33
        assert abs(m1['cogs_duty'] - 483.33) < 1.0, (
            f"Month 1 duty {m1['cogs_duty']:.2f} expected ~483.33 (only AL-002 has tariff)"
        )


class TestForecastReportUI:
    """Load the HTML report in a browser and validate rendered figures."""

    def test_page_loads(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        expect(page.locator('h1')).to_contain_text('MML Consumer Products')
        ss(page, '01_overview')

    def test_kpi_revenue_displayed(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        kpi_rev = parse_nzd(page.locator('#kpi-revenue').inner_text())
        expected = pipeline_output['kpis']['total_revenue']
        assert abs(kpi_rev - expected) < 1.0, (
            f'Displayed revenue {kpi_rev:,.2f} != pipeline {expected:,.2f}'
        )

    def test_kpi_ebitda_displayed(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        kpi_ebitda = parse_nzd(page.locator('#kpi-ebitda').inner_text())
        expected = pipeline_output['kpis']['total_ebitda']
        assert abs(kpi_ebitda - expected) < 1.0

    def test_kpi_ending_cash_displayed(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        kpi_cash = parse_nzd(page.locator('#kpi-ending-cash').inner_text())
        expected = pipeline_output['kpis']['ending_cash']
        assert abs(kpi_cash - expected) < 1.0

    def test_kpi_cash_low_displayed(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        kpi_low = parse_nzd(page.locator('#kpi-cash-low').inner_text())
        expected = pipeline_output['kpis']['cash_low_value']
        assert abs(kpi_low - expected) < 1.0

    def test_pnl_table_has_12_rows(self, page: Page, report_url):
        page.goto(report_url)
        rows = page.locator('#pnl-table tbody tr')
        assert rows.count() == 12, f'P&L table has {rows.count()} rows, expected 12'

    def test_cf_table_has_12_rows(self, page: Page, report_url):
        page.goto(report_url)
        rows = page.locator('#cf-table tbody tr')
        assert rows.count() == 12

    def test_bs_table_has_12_rows(self, page: Page, report_url):
        page.goto(report_url)
        rows = page.locator('#bs-table tbody tr')
        assert rows.count() == 12

    def test_all_verifier_checks_pass_in_ui(self, page: Page, report_url, pipeline_output):
        page.goto(report_url)
        # All rows in cmp-table should show PASS
        fail_cells = page.locator('#cmp-table .cmp-fail')
        # Only the footer "ALL PASS" span will exist if all passed
        assert pipeline_output['comparison_passed'], 'Pipeline comparison failed'
        assert fail_cells.count() == 0, (
            f'{fail_cells.count()} comparison check(s) show FAIL in report'
        )

    def test_screenshot_pnl(self, page: Page, report_url):
        page.goto(report_url)
        page.locator('#pnl-table').scroll_into_view_if_needed()
        ss(page, '02_pnl_table')

    def test_screenshot_cashflow(self, page: Page, report_url):
        page.goto(report_url)
        page.locator('#cf-table').scroll_into_view_if_needed()
        ss(page, '03_cashflow_table')

    def test_screenshot_comparison(self, page: Page, report_url):
        page.goto(report_url)
        page.locator('#cmp-table').scroll_into_view_if_needed()
        ss(page, '04_verification_table')

    def test_full_page_screenshot(self, page: Page, report_url):
        page.goto(report_url)
        path = SCREENSHOTS_DIR / '00_full_report.png'
        page.screenshot(path=str(path), full_page=True)
        print(f'Full page screenshot: {path}')
