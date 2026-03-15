# conftest.py — mml.forecasting
#
# Self-contained Odoo stub installer for the mml.forecasting workspace.
# Mirrors the pattern in mml.roq.model/conftest.py.
#
# Installs lightweight odoo.* stubs so pure-Python structural tests can
# import model classes without a running Odoo instance.
#
# Registers mml_forecast_core and mml_forecast_financial into sys.modules
# under both their short names and odoo.addons.* so intra-addon imports resolve.

import sys
import types
import pathlib
import pytest

_ROOT = pathlib.Path(__file__).parent

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _install_odoo_stubs():
    """Build and register lightweight odoo stubs in sys.modules (idempotent)."""
    if 'odoo' in sys.modules and hasattr(sys.modules['odoo'], '_stubbed'):
        return

    # ---- odoo.fields ----
    odoo_fields = types.ModuleType('odoo.fields')

    class _BaseField:
        def __init__(self, *args, **kwargs):
            self._kwargs = kwargs
            self.default = kwargs.get('default')
            self.string = args[0] if args else kwargs.get('string', '')

        def __set_name__(self, owner, name):
            self._attr_name = name
            if '_fields_meta' not in owner.__dict__:
                owner._fields_meta = {}
            owner._fields_meta[name] = self

    class Selection(_BaseField):
        def __init__(self, selection=None, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.selection = selection or []

    for _fname in ('Boolean', 'Char', 'Date', 'Float', 'Integer', 'Text',
                    'Html', 'Binary', 'Json', 'Many2one', 'One2many', 'Many2many'):
        setattr(odoo_fields, _fname, type(_fname, (_BaseField,), {}))

    class Datetime(_BaseField):
        @classmethod
        def now(cls):
            import datetime
            return datetime.datetime.utcnow()

    odoo_fields.Selection = Selection
    odoo_fields.Datetime = Datetime

    # ---- odoo.models ----
    odoo_models = types.ModuleType('odoo.models')

    class Model:
        _inherit = None
        _name = None
        _fields_meta = {}
        def write(self, vals): pass
        def ensure_one(self): pass
        def search(self, domain, **kwargs): return []
        def sudo(self): return self
        def create(self, vals): pass

    class AbstractModel(Model): pass
    class TransientModel(Model): pass

    class Constraint:
        """Stub for odoo.models.Constraint (SQL-level unique/check constraints)."""
        def __init__(self, *args, **kwargs):
            pass

        def __set_name__(self, owner, name):
            pass

    odoo_models.Model = Model
    odoo_models.AbstractModel = AbstractModel
    odoo_models.TransientModel = TransientModel
    odoo_models.Constraint = Constraint

    # ---- odoo.api ----
    odoo_api = types.ModuleType('odoo.api')
    odoo_api.model = lambda f: f
    odoo_api.depends = lambda *args: (lambda f: f)
    odoo_api.constrains = lambda *args: (lambda f: f)
    odoo_api.onchange = lambda *args: (lambda f: f)
    odoo_api.model_create_multi = lambda f: f

    # ---- odoo.exceptions ----
    odoo_exceptions = types.ModuleType('odoo.exceptions')
    class ValidationError(Exception): pass
    class UserError(Exception): pass
    odoo_exceptions.ValidationError = ValidationError
    odoo_exceptions.UserError = UserError

    # ---- odoo.tests ----
    import unittest
    odoo_tests = types.ModuleType('odoo.tests')
    class TransactionCase(unittest.TestCase):
        """Stub: self.env NOT available without Odoo."""
    def tagged(*args):
        def decorator(cls): return cls
        return decorator
    odoo_tests.TransactionCase = TransactionCase
    odoo_tests.tagged = tagged

    odoo_tests_common = types.ModuleType('odoo.tests.common')
    odoo_tests_common.TransactionCase = TransactionCase

    # ---- odoo.http ----
    odoo_http = types.ModuleType('odoo.http')
    odoo_http.Controller = type('Controller', (), {})
    odoo_http.route = lambda *a, **kw: (lambda f: f)
    odoo_http.request = None

    # ---- odoo root ----
    odoo = types.ModuleType('odoo')
    odoo._stubbed = True
    odoo._ = lambda s: s
    odoo.models = odoo_models
    odoo.fields = odoo_fields
    odoo.api = odoo_api
    odoo.exceptions = odoo_exceptions
    odoo.tests = odoo_tests
    odoo.http = odoo_http

    sys.modules['odoo'] = odoo
    sys.modules['odoo.models'] = odoo_models
    sys.modules['odoo.fields'] = odoo_fields
    sys.modules['odoo.api'] = odoo_api
    sys.modules['odoo.exceptions'] = odoo_exceptions
    sys.modules['odoo.tests'] = odoo_tests
    sys.modules['odoo.tests.common'] = odoo_tests_common
    sys.modules['odoo.http'] = odoo_http

    odoo_addons = types.ModuleType('odoo.addons')
    sys.modules['odoo.addons'] = odoo_addons
    odoo.addons = odoo_addons

    # Register mml_forecast_core and mml_forecast_financial
    for addon_name in ('mml_forecast_core', 'mml_forecast_financial'):
        addon_path = _ROOT / addon_name
        full_name = f'odoo.addons.{addon_name}'
        if full_name not in sys.modules:
            pkg = types.ModuleType(full_name)
            pkg.__path__ = [str(addon_path)]
            pkg.__package__ = full_name
            sys.modules[full_name] = pkg
            if addon_name not in sys.modules:
                sys.modules[addon_name] = pkg
            setattr(odoo_addons, addon_name, pkg)
        for sub in ('models', 'services', 'wizard', 'wizards'):
            sub_full = f'{full_name}.{sub}'
            if sub_full not in sys.modules:
                sub_pkg = types.ModuleType(sub_full)
                sub_pkg.__path__ = [str(addon_path / sub)]
                sub_pkg.__package__ = sub_full
                sys.modules[sub_full] = sub_pkg


_install_odoo_stubs()


def pytest_collection_modifyitems(config, items):
    """Auto-mark TransactionCase tests as odoo_integration (requires odoo-bin)."""
    from odoo.tests import TransactionCase
    for item in items:
        if isinstance(item, pytest.Class):
            continue
        cls = getattr(item, 'cls', None)
        if cls is not None and issubclass(cls, TransactionCase):
            item.add_marker(pytest.mark.odoo_integration)
