"""
Pure-Python TDD tests — enforce ex-GST pricelists in forecast generation.

A misconfigured GST-inclusive pricelist would overstate 12-month forecast
revenue by the GST component (15% in NZ). The wizard previously emitted a
log warning only; this suite locks in the new behaviour: a hard
ValidationError is raised before any revenue line is created.

Run: pytest mml_forecast_financial/tests/test_pricelist_gst_constraint.py -q
"""
import importlib

import pytest

from odoo.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Fake records — minimal duck-typed helpers (mirroring test_model_fields.py)
# ---------------------------------------------------------------------------

class _FakeRecordset(list):
    """List subclass with .mapped()/.filtered() for traversing fake collections."""

    def mapped(self, field):
        results = []
        for item in self:
            value = getattr(item, field, None)
            if isinstance(value, _FakeRecordset):
                results.extend(value)
            elif value is not None and value is not False:
                results.append(value)
        return _FakeRecordset(results)

    def filtered(self, predicate):
        return _FakeRecordset([item for item in self if predicate(item)])

    def __bool__(self):
        return len(self) > 0


class _FakeTax:
    def __init__(self, name='GST 15%', price_include=False, amount=15.0):
        self.name = name
        self.display_name = name
        self.price_include = price_include
        self.amount = amount


class _FakePricelist:
    def __init__(self, name, tax_ids=None):
        self.id = id(self)
        self.name = name
        self.display_name = name
        # Odoo pricelists do not carry tax_ids directly, but pricelist items do.
        # For test ergonomics, expose the linked tax(es) on the pricelist itself
        # via tax_ids; the validator inspects this collection.
        self.tax_ids = _FakeRecordset(tax_ids or [])


class _FakePartner:
    def __init__(self, name, pricelist=None):
        self.id = id(self)
        self.name = name
        self.display_name = name
        self.property_product_pricelist = pricelist


class _FakeCustomerTerm:
    def __init__(self, partner):
        self.id = id(self)
        self.partner_id = partner


class _FakeConfig:
    def __init__(self, customer_terms=None, name='Test Forecast'):
        self.id = id(self)
        self.name = name
        self.customer_term_ids = _FakeRecordset(customer_terms or [])


# ---------------------------------------------------------------------------
# Wizard helper — exposes the validator without needing an Odoo env
# ---------------------------------------------------------------------------

def _get_wizard_class():
    """Import ForecastGenerateWizard, returning the class (not an instance)."""
    mod = importlib.import_module(
        'mml_forecast_financial.wizards.forecast_generate_wizard'
    )
    return mod.ForecastGenerateWizard


def _validate(config):
    """Invoke the validator on a fake config without instantiating the wizard."""
    cls = _get_wizard_class()
    # The validator is a regular method that only reads config — it does not
    # touch self.env. Calling it as an unbound method with `None` for self is
    # safe and keeps the test pure-Python.
    return cls._validate_pricelists_ex_gst(None, config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPricelistGstConstraint:
    """The wizard must reject GST-inclusive pricelists before generating."""

    def test_validator_method_exists_on_wizard(self):
        """Locking in the public surface: _validate_pricelists_ex_gst() exists."""
        cls = _get_wizard_class()
        assert hasattr(cls, '_validate_pricelists_ex_gst'), (
            'ForecastGenerateWizard must expose _validate_pricelists_ex_gst() '
            'so the constraint can be unit-tested without Odoo.'
        )

    def test_passes_when_no_customer_terms(self):
        """Empty customer_term_ids must not raise (nothing to validate)."""
        config = _FakeConfig(customer_terms=[])
        # No exception expected
        _validate(config)

    def test_passes_when_partner_has_no_pricelist(self):
        """Partner without a pricelist falls back to list_price; not an error."""
        partner = _FakePartner('Walk-in Customer', pricelist=None)
        config = _FakeConfig(customer_terms=[_FakeCustomerTerm(partner)])
        _validate(config)

    def test_passes_when_pricelist_tax_is_ex_gst(self):
        """A pricelist whose linked tax has price_include=False is valid."""
        ex_gst_tax = _FakeTax(name='GST 15% (excl)', price_include=False)
        pricelist = _FakePricelist('Wholesale ex-GST', tax_ids=[ex_gst_tax])
        partner = _FakePartner('Briscoes', pricelist=pricelist)
        config = _FakeConfig(customer_terms=[_FakeCustomerTerm(partner)])
        _validate(config)

    def test_passes_when_pricelist_has_no_tax(self):
        """A pricelist with no linked taxes is treated as ex-GST (default)."""
        pricelist = _FakePricelist('Net Pricelist', tax_ids=[])
        partner = _FakePartner('Animates', pricelist=pricelist)
        config = _FakeConfig(customer_terms=[_FakeCustomerTerm(partner)])
        _validate(config)

    def test_raises_when_pricelist_tax_is_gst_inclusive(self):
        """A GST-inclusive pricelist must trigger a ValidationError."""
        inc_gst_tax = _FakeTax(name='GST 15% (incl)', price_include=True)
        pricelist = _FakePricelist('Retail incl-GST', tax_ids=[inc_gst_tax])
        partner = _FakePartner('Harvey Norman', pricelist=pricelist)
        config = _FakeConfig(customer_terms=[_FakeCustomerTerm(partner)])

        with pytest.raises(ValidationError) as exc_info:
            _validate(config)

        message = str(exc_info.value)
        assert 'GST-exclusive' in message, (
            f'Error must explain the constraint clearly. Got: {message}'
        )
        assert 'Retail incl-GST' in message, (
            f'Error must name the offending pricelist. Got: {message}'
        )
        assert 'Harvey Norman' in message, (
            f'Error must name the customer/term. Got: {message}'
        )
        assert 'price_include' in message, (
            f'Error must direct the user to the fix. Got: {message}'
        )

    def test_error_lists_every_offending_pricelist(self):
        """When multiple pricelists are GST-inclusive, all must be reported."""
        bad_tax_a = _FakeTax(name='AU GST incl', price_include=True)
        bad_tax_b = _FakeTax(name='UK VAT incl', price_include=True)
        pricelist_a = _FakePricelist('AU Retail', tax_ids=[bad_tax_a])
        pricelist_b = _FakePricelist('UK Retail', tax_ids=[bad_tax_b])
        partner_a = _FakePartner('AU Customer', pricelist=pricelist_a)
        partner_b = _FakePartner('UK Customer', pricelist=pricelist_b)
        config = _FakeConfig(customer_terms=[
            _FakeCustomerTerm(partner_a),
            _FakeCustomerTerm(partner_b),
        ])

        with pytest.raises(ValidationError) as exc_info:
            _validate(config)

        message = str(exc_info.value)
        assert 'AU Retail' in message
        assert 'UK Retail' in message

    def test_passes_when_mixed_terms_all_resolve_to_ex_gst(self):
        """Several terms, all clean → no error."""
        ok_tax = _FakeTax(price_include=False)
        pricelist_a = _FakePricelist('Wholesale A', tax_ids=[ok_tax])
        pricelist_b = _FakePricelist('Wholesale B', tax_ids=[ok_tax])
        partner_a = _FakePartner('Customer A', pricelist=pricelist_a)
        partner_b = _FakePartner('Customer B', pricelist=pricelist_b)
        partner_c = _FakePartner('Customer C', pricelist=None)
        config = _FakeConfig(customer_terms=[
            _FakeCustomerTerm(partner_a),
            _FakeCustomerTerm(partner_b),
            _FakeCustomerTerm(partner_c),
        ])
        _validate(config)

    def test_warning_no_longer_used_in_get_sell_price(self):
        """
        Regression guard: the prior implementation emitted a per-product
        warning from _get_sell_price(). After this change, the warning has
        moved upstream to a hard constraint, so _get_sell_price() must no
        longer call _logger.warning() about GST.
        """
        import inspect
        cls = _get_wizard_class()
        source = inspect.getsource(cls._get_sell_price)
        assert 'GST-inclusive pricelists will overstate' not in source, (
            'The advisory warning in _get_sell_price() must be removed once '
            'the constraint blocks generation upfront.'
        )
