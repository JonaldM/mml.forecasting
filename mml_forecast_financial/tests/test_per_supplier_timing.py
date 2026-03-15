"""
Pure-Python tests for per-supplier cashflow timing logic.
Tests the supplier_term_map lookup and fallback behaviour used in
_generate_cashflow_lines().

Run: pytest mml_forecast_financial/tests/test_per_supplier_timing.py -q
"""
import math


_DEFAULT_DEPOSIT_MONTHS = 3
_DEFAULT_TRANSIT_MONTHS = 1
_DEFAULT_DEPOSIT_PCT = 0.30


def resolve_supplier_timing(supplier_id, supplier_term_map):
    """
    Mirror of the per-supplier timing resolution in _generate_cashflow_lines().
    Returns (deposit_months_back, transit_months_back, deposit_pct).
    """
    term = supplier_term_map.get(supplier_id)
    if term:
        return (
            math.ceil(term['deposit_trigger_days'] / 30.0),
            math.ceil(term['transit_days'] / 30.0),
            term['deposit_pct'] / 100.0,
        )
    return (_DEFAULT_DEPOSIT_MONTHS, _DEFAULT_TRANSIT_MONTHS, _DEFAULT_DEPOSIT_PCT)


class TestPerSupplierTiming:
    def _make_term(self, deposit_days, transit_days, deposit_pct):
        return {
            'deposit_trigger_days': deposit_days,
            'transit_days': transit_days,
            'deposit_pct': deposit_pct,
        }

    def test_known_supplier_uses_its_term(self):
        supplier_id = 42
        term_map = {42: self._make_term(60, 22, 30)}
        dep, trans, pct = resolve_supplier_timing(supplier_id, term_map)
        assert dep == 2   # ceil(60/30)
        assert trans == 1  # ceil(22/30)
        assert pct == 0.30

    def test_different_supplier_long_lead(self):
        supplier_id = 7
        term_map = {7: self._make_term(90, 45, 40)}
        dep, trans, pct = resolve_supplier_timing(supplier_id, term_map)
        assert dep == 3   # ceil(90/30)
        assert trans == 2  # ceil(45/30)
        assert pct == 0.40

    def test_unknown_supplier_uses_defaults(self):
        dep, trans, pct = resolve_supplier_timing(99, {})
        assert dep == _DEFAULT_DEPOSIT_MONTHS
        assert trans == _DEFAULT_TRANSIT_MONTHS
        assert pct == _DEFAULT_DEPOSIT_PCT

    def test_none_supplier_id_uses_defaults(self):
        dep, trans, pct = resolve_supplier_timing(None, {42: self._make_term(60, 22, 30)})
        assert dep == _DEFAULT_DEPOSIT_MONTHS

    def test_deposit_and_balance_pct_sum_to_one(self):
        supplier_id = 5
        term_map = {5: self._make_term(75, 30, 35)}
        dep, trans, deposit_pct = resolve_supplier_timing(supplier_id, term_map)
        balance_pct = 1.0 - deposit_pct
        assert abs(deposit_pct + balance_pct - 1.0) < 1e-9
