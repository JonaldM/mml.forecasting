# Forecasting Suite Refactor: Three-Module Architecture

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Consolidate `mml_roq_forecast` (demand) and `mml_financial_forecast` (scaffold) into a clean three-module suite — `mml_forecast_core` / `mml_forecast_demand` / `mml_forecast_financial` — all living in the `mml.forecasting` repo.

**Architecture:** Four sequential sprints. Each sprint leaves the repo in a working, installable state. Core is extracted first (shared models), then demand is migrated (ROQ renamed), then financial is refactored (scaffold cleaned up), then the cashflow engine is rewritten with full supplier payment timing. No module directly imports another — only standard Odoo model dependencies.

**Tech Stack:** Odoo 19, Python 3, standard ORM, `dateutil.relativedelta`, `numpy`/`scipy` (demand module only)

**Repo:** `mml.forecasting/` at `https://github.com/JonaldM/mml.forecasting`
**Source for demand migration:** `E:\ClaudeCode\projects\mml.odoo.apps\roq.model\mml_roq_forecast\`

---

## Context: What Exists Today

```
mml.forecasting/
  mml_financial_forecast/
    mml_financial_forecast/        ← double-nested Odoo module (scaffold only)
      __manifest__.py
      models/                      ← forecast.config, fx.rate, customer.term,
      wizard/                         revenue, cogs, pnl, cashflow, opex lines
      views/
      ...
  docs/
  mml_forecast_sprint_brief.md
```

```
roq.model/
  mml_roq_forecast/               ← fully-implemented ROQ module (sprints 0–4 merged)
    models/                       ← roq.forecast.run/line, roq.shipment.group,
    services/                        roq.forward.plan, roq.port, product/partner/
    views/                           warehouse extensions, etc.
    tests/                        ← comprehensive test suite
    ...
```

## Target State

```
mml.forecasting/
  mml_forecast_core/              ← NEW: shared infra, application=False
  mml_forecast_demand/            ← NEW: migrated from mml_roq_forecast
  mml_forecast_financial/         ← NEW: refactored from scaffold
  docs/plans/
```

---

## Sprint 1: `mml_forecast_core`

**Goal:** Create the shared infrastructure module. Extract `forecast.config`, `forecast.fx.rate`, `forecast.customer.term` from the scaffold. Add two new models: `forecast.origin.port` and `forecast.supplier.term`. Define the top-level Forecasting app menu.

**Pre-condition:** Working in `mml.forecasting/` repo root. The scaffold in `mml_financial_forecast/mml_financial_forecast/` is untouched until Sprint 3.

---

### Task 1.1: Scaffold `mml_forecast_core` module

**Files to create:**
- `mml_forecast_core/__manifest__.py`
- `mml_forecast_core/__init__.py`
- `mml_forecast_core/models/__init__.py`
- `mml_forecast_core/security/ir.model.access.csv`
- `mml_forecast_core/static/description/icon.png` (copy from scaffold or use placeholder)

**Step 1: Create the manifest**

```python
# mml_forecast_core/__manifest__.py
{
    'name': 'MML Forecast Core',
    'version': '19.0.1.0.0',
    'summary': 'Shared infrastructure for MML Forecasting Suite',
    'author': 'MML Consumer Products Ltd',
    'category': 'Forecasting',
    'depends': ['base', 'product', 'sale', 'purchase', 'account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/default_data.xml',
        'views/forecast_origin_port_views.xml',
        'views/forecast_supplier_term_views.xml',
        'views/forecast_fx_rate_views.xml',
        'views/forecast_customer_term_views.xml',
        'views/forecast_config_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'web_icon': 'mml_forecast_core,static/description/icon.png',
    'license': 'LGPL-3',
}
```

> Note: `application=True` so the "Forecasting" home screen tile appears. Core is the entry point for the suite. Demand and Financial hang off its menu.

**Step 2: Create `__init__.py` files**

```python
# mml_forecast_core/__init__.py
from . import models
```

```python
# mml_forecast_core/models/__init__.py
# populated in later tasks
```

**Step 3: Create empty security file**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
```

**Step 4: Verify directory structure exists, then commit**

```bash
ls mml_forecast_core/
git add mml_forecast_core/
git commit -m "feat(core): scaffold mml_forecast_core module"
```

---

### Task 1.2: Add `forecast.origin.port` model

This replaces and supersedes `roq.port` from the demand module. It adds `transit_days_nz` which the financial cashflow engine needs. The demand module will migrate its port data here in Sprint 2.

**Files:**
- Create: `mml_forecast_core/models/forecast_origin_port.py`
- Modify: `mml_forecast_core/models/__init__.py`
- Create: `mml_forecast_core/views/forecast_origin_port_views.xml`

**Step 1: Write the model**

```python
# mml_forecast_core/models/forecast_origin_port.py
from odoo import models, fields, api


class ForecastOriginPort(models.Model):
    _name = 'forecast.origin.port'
    _description = 'Origin Port (for freight transit time calculation)'
    _order = 'code'

    code = fields.Char(
        string='UN/LOCODE', size=5, required=True, index=True,
        help='5-character UN/LOCODE, e.g. CNSHA for Shanghai.',
    )
    name = fields.Char(string='Port Name', required=True)
    country_id = fields.Many2one('res.country', string='Country')
    transit_days_nz = fields.Integer(
        string='Transit Days to NZ',
        default=22,
        help='Sea freight transit days to NZ port. Shanghai ~22, Ningbo ~20, Shenzhen/Yantian ~18.',
    )
    notes = fields.Char(string='Notes')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Port UN/LOCODE must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].upper()
        return super().write(vals)

    def name_get(self):
        return [(p.id, f'{p.code} — {p.name}') for p in self]
```

**Step 2: Update `models/__init__.py`**

```python
# mml_forecast_core/models/__init__.py
from . import forecast_origin_port
```

**Step 3: Create the view**

```xml
<!-- mml_forecast_core/views/forecast_origin_port_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_forecast_origin_port_list" model="ir.ui.view">
        <field name="name">forecast.origin.port.list</field>
        <field name="model">forecast.origin.port</field>
        <field name="arch" type="xml">
            <list string="Origin Ports" editable="bottom">
                <field name="code"/>
                <field name="name"/>
                <field name="country_id"/>
                <field name="transit_days_nz"/>
                <field name="notes"/>
            </list>
        </field>
    </record>

    <record id="view_forecast_origin_port_form" model="ir.ui.view">
        <field name="name">forecast.origin.port.form</field>
        <field name="model">forecast.origin.port</field>
        <field name="arch" type="xml">
            <form string="Origin Port">
                <sheet>
                    <group>
                        <field name="code"/>
                        <field name="name"/>
                        <field name="country_id"/>
                        <field name="transit_days_nz"/>
                        <field name="notes"/>
                        <field name="active"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_forecast_origin_port" model="ir.actions.act_window">
        <field name="name">Origin Ports</field>
        <field name="res_model">forecast.origin.port</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

**Step 4: Add security row**

```csv
# add to mml_forecast_core/security/ir.model.access.csv
access_forecast_origin_port_user,forecast.origin.port user,model_forecast_origin_port,base.group_user,1,0,0,0
access_forecast_origin_port_manager,forecast.origin.port manager,model_forecast_origin_port,base.group_system,1,1,1,1
```

**Step 5: Add default port data**

```xml
<!-- mml_forecast_core/data/default_data.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="port_cnsha" model="forecast.origin.port">
        <field name="code">CNSHA</field>
        <field name="name">Shanghai</field>
        <field name="country_id" ref="base.cn"/>
        <field name="transit_days_nz">22</field>
    </record>
    <record id="port_cnngb" model="forecast.origin.port">
        <field name="code">CNNGB</field>
        <field name="name">Ningbo</field>
        <field name="country_id" ref="base.cn"/>
        <field name="transit_days_nz">20</field>
    </record>
    <record id="port_cnszx" model="forecast.origin.port">
        <field name="code">CNSZX</field>
        <field name="name">Shenzhen / Yantian</field>
        <field name="country_id" ref="base.cn"/>
        <field name="transit_days_nz">18</field>
    </record>
</odoo>
```

**Step 6: Commit**

```bash
git add mml_forecast_core/
git commit -m "feat(core): add forecast.origin.port model with transit days"
```

---

### Task 1.3: Add `forecast.supplier.term` model

Per-forecast-config supplier payment configuration. This is **financially-scoped** (deposit %, payment method, lead time for cash flow back-calculation). Distinct from ROQ's operational `res.partner` supplier fields.

**Files:**
- Create: `mml_forecast_core/models/forecast_supplier_term.py`
- Modify: `mml_forecast_core/models/__init__.py`
- Create: `mml_forecast_core/views/forecast_supplier_term_views.xml`

**Step 1: Write the model**

```python
# mml_forecast_core/models/forecast_supplier_term.py
from odoo import models, fields


class ForecastSupplierTerm(models.Model):
    _name = 'forecast.supplier.term'
    _description = 'Forecast Supplier Payment Term'
    _order = 'supplier_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier / Factory',
        required=True,
        domain=[('supplier_rank', '>', 0)],
    )
    deposit_pct = fields.Float(
        string='Deposit %',
        default=30.0,
        help='Deposit as percentage of FOB value. 0 = no deposit.',
    )
    deposit_trigger_days = fields.Integer(
        string='Deposit Due (days after PO)',
        default=0,
        help='Days after PO placement that deposit is due. 0 = immediate.',
    )
    production_lead_days = fields.Integer(
        string='Production Lead Time (days)',
        default=45,
        help='Calendar days from PO placement to cargo ready / BL issued.',
    )
    origin_port_id = fields.Many2one(
        'forecast.origin.port',
        string='Origin Port',
        help='FOB port — determines sea transit days to NZ.',
    )
    payment_method = fields.Selection([
        ('tt', 'Telegraphic Transfer (TT)'),
        ('lc', 'Letter of Credit (LC)'),
    ], string='Payment Method', default='tt')
    notes = fields.Char(string='Notes')

    @property
    def transit_days(self):
        """Sea transit days from origin port to NZ."""
        return self.origin_port_id.transit_days_nz if self.origin_port_id else 22

    @property
    def total_lead_days(self):
        """Total days from PO placement to cargo arrival at NZ port."""
        return self.production_lead_days + self.transit_days
```

**Step 2: Update `models/__init__.py`**

```python
from . import forecast_origin_port
from . import forecast_supplier_term
```

**Step 3: Create the view**

```xml
<!-- mml_forecast_core/views/forecast_supplier_term_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_forecast_supplier_term_list" model="ir.ui.view">
        <field name="name">forecast.supplier.term.list</field>
        <field name="model">forecast.supplier.term</field>
        <field name="arch" type="xml">
            <list string="Supplier Payment Terms" editable="bottom">
                <field name="supplier_id"/>
                <field name="deposit_pct"/>
                <field name="deposit_trigger_days"/>
                <field name="production_lead_days"/>
                <field name="origin_port_id"/>
                <field name="payment_method"/>
                <field name="notes"/>
            </list>
        </field>
    </record>
</odoo>
```

**Step 4: Add security row**

```csv
access_forecast_supplier_term_user,forecast.supplier.term user,model_forecast_supplier_term,base.group_user,1,0,0,0
access_forecast_supplier_term_manager,forecast.supplier.term manager,model_forecast_supplier_term,base.group_system,1,1,1,1
```

**Step 5: Commit**

```bash
git add mml_forecast_core/
git commit -m "feat(core): add forecast.supplier.term model"
```

---

### Task 1.4: Move `forecast.fx.rate` from scaffold to core

**Files:**
- Create: `mml_forecast_core/models/forecast_fx_rate.py`
- Copy source from: `mml_financial_forecast/mml_financial_forecast/models/forecast_fx_rate.py`
- Create: `mml_forecast_core/views/forecast_fx_rate_views.xml`
- Copy source from: `mml_financial_forecast/mml_financial_forecast/views/forecast_fx_rate_views.xml`

**Step 1: Copy the model** (file content is identical — no changes needed)

```bash
cp mml_financial_forecast/mml_financial_forecast/models/forecast_fx_rate.py \
   mml_forecast_core/models/forecast_fx_rate.py
```

**Step 2: Update `models/__init__.py`**

```python
from . import forecast_origin_port
from . import forecast_supplier_term
from . import forecast_fx_rate
```

**Step 3: Copy the view**

```bash
cp mml_financial_forecast/mml_financial_forecast/views/forecast_fx_rate_views.xml \
   mml_forecast_core/views/forecast_fx_rate_views.xml
```

Update the view file — change `mml_financial_forecast` references to `mml_forecast_core`:
```xml
<!-- Only change: web_icon and external_id prefixes if any -->
<!-- The model name forecast.fx.rate stays identical -->
```

**Step 4: Add security row**

```csv
access_forecast_fx_rate_user,forecast.fx.rate user,model_forecast_fx_rate,base.group_user,1,0,0,0
access_forecast_fx_rate_manager,forecast.fx.rate manager,model_forecast_fx_rate,base.group_system,1,1,1,1
```

**Step 5: Commit**

```bash
git add mml_forecast_core/
git commit -m "feat(core): add forecast.fx.rate model (moved from scaffold)"
```

---

### Task 1.5: Move `forecast.customer.term` from scaffold to core

**Files:**
- Create: `mml_forecast_core/models/forecast_customer_term.py`
- Copy source from: `mml_financial_forecast/mml_financial_forecast/models/forecast_customer_term.py`
- Create: `mml_forecast_core/views/forecast_customer_term_views.xml`

**Step 1: Copy the model** (content identical)

```bash
cp mml_financial_forecast/mml_financial_forecast/models/forecast_customer_term.py \
   mml_forecast_core/models/forecast_customer_term.py

cp mml_financial_forecast/mml_financial_forecast/views/forecast_customer_term_views.xml \
   mml_forecast_core/views/forecast_customer_term_views.xml
```

**Step 2: Update `models/__init__.py`**

```python
from . import forecast_origin_port
from . import forecast_supplier_term
from . import forecast_fx_rate
from . import forecast_customer_term
```

**Step 3: Add security rows**

```csv
access_forecast_customer_term_user,forecast.customer.term user,model_forecast_customer_term,base.group_user,1,0,0,0
access_forecast_customer_term_manager,forecast.customer.term manager,model_forecast_customer_term,base.group_system,1,1,1,1
```

**Step 4: Commit**

```bash
git add mml_forecast_core/
git commit -m "feat(core): add forecast.customer.term model (moved from scaffold)"
```

---

### Task 1.6: Move `forecast.config` from scaffold to core (with additions)

This is the central config model. Two additions vs the scaffold:
1. `tax_id` — Many2one to `account.tax` (replaces the hardcoded 15% GST in the wizard)
2. `supplier_term_ids` — One2many to `forecast.supplier.term`

**Files:**
- Create: `mml_forecast_core/models/forecast_config.py`
- Create: `mml_forecast_core/views/forecast_config_views.xml`

**Step 1: Write the model** — scaffold content plus additions

```python
# mml_forecast_core/models/forecast_config.py
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


class ForecastConfig(models.Model):
    _name = 'forecast.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Financial Forecast Configuration'
    _order = 'create_date desc'

    name = fields.Char(string='Forecast Name', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('locked', 'Locked'),
    ], default='draft', string='Status', tracking=True)

    # --- Period ---
    date_start = fields.Date(string='Forecast Start', required=True)
    horizon_months = fields.Integer(string='Horizon (months)', default=12, required=True)
    date_end = fields.Date(
        string='Forecast End',
        compute='_compute_date_end',
        store=True,
    )

    # --- Scenario ---
    scenario = fields.Selection([
        ('base', 'Base Case'),
        ('optimistic', 'Optimistic'),
        ('pessimistic', 'Pessimistic'),
        ('custom', 'Custom'),
    ], default='base', required=True, string='Scenario')
    volume_adjustment_pct = fields.Float(
        string='Volume Adjustment %',
        default=0.0,
        help='Percentage adjustment to unit forecast. E.g. -20 for pessimistic.',
    )
    freight_rate_cbm = fields.Float(
        string='Freight Rate ($/CBM)',
        default=100.0,
        required=True,
    )

    # --- Import tax (NEW — replaces hardcoded 15% GST) ---
    tax_id = fields.Many2one(
        'account.tax',
        string='Import Tax',
        domain=[('type_tax_use', '=', 'purchase')],
        help=(
            'Purchase tax applied on import (GST/VAT). '
            'NZ = 15% GST, AU = 10% GST, UK = 20% VAT. '
            'Used in cash flow duty calculations.'
        ),
    )

    # --- Relational ---
    fx_rate_ids = fields.One2many('forecast.fx.rate', 'config_id', string='FX Rates')
    customer_term_ids = fields.One2many(
        'forecast.customer.term', 'config_id', string='Customer Payment Terms',
    )
    supplier_term_ids = fields.One2many(
        'forecast.supplier.term', 'config_id', string='Supplier Payment Terms',
    )
    opex_line_ids = fields.One2many('forecast.opex.line', 'config_id', string='Operating Expenses')
    revenue_line_ids = fields.One2many('forecast.revenue.line', 'config_id', string='Revenue Lines')
    cogs_line_ids = fields.One2many('forecast.cogs.line', 'config_id', string='COGS Lines')
    pnl_line_ids = fields.One2many('forecast.pnl.line', 'config_id', string='P&L Summary')
    cashflow_line_ids = fields.One2many(
        'forecast.cashflow.line', 'config_id', string='Cash Flow Lines',
    )

    # --- Totals ---
    total_revenue = fields.Float(
        string='Total Revenue', compute='_compute_totals', store=True,
    )
    total_cogs = fields.Float(
        string='Total COGS', compute='_compute_totals', store=True,
    )
    total_gross_margin = fields.Float(
        string='Total Gross Margin', compute='_compute_totals', store=True,
    )
    gross_margin_pct = fields.Float(
        string='GM %', compute='_compute_totals', store=True,
    )

    notes = fields.Html(string='Notes')

    @api.depends('date_start', 'horizon_months')
    def _compute_date_end(self):
        for rec in self:
            if rec.date_start and rec.horizon_months:
                rec.date_end = rec.date_start + relativedelta(months=rec.horizon_months, days=-1)
            else:
                rec.date_end = False

    @api.depends('pnl_line_ids.revenue', 'pnl_line_ids.total_cogs', 'pnl_line_ids.gross_margin')
    def _compute_totals(self):
        for rec in self:
            lines = rec.pnl_line_ids
            rec.total_revenue = sum(lines.mapped('revenue'))
            rec.total_cogs = sum(lines.mapped('total_cogs'))
            rec.total_gross_margin = sum(lines.mapped('gross_margin'))
            rec.gross_margin_pct = (
                (rec.total_gross_margin / rec.total_revenue * 100)
                if rec.total_revenue else 0.0
            )

    def action_generate_forecast(self):
        self.ensure_one()
        self.env['forecast.generate.wizard'].with_context(active_id=self.id).generate(self)
        self.state = 'generated'

    def action_reset_draft(self):
        self.ensure_one()
        self.revenue_line_ids.unlink()
        self.cogs_line_ids.unlink()
        self.pnl_line_ids.unlink()
        self.cashflow_line_ids.unlink()
        self.state = 'draft'

    def action_lock(self):
        self.ensure_one()
        self.state = 'locked'

    def action_duplicate_scenario(self):
        self.ensure_one()
        new = self.copy(default={'name': f'{self.name} (Copy)', 'state': 'draft'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'forecast.config',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }
```

**Step 2: Update `models/__init__.py`**

```python
from . import forecast_origin_port
from . import forecast_supplier_term
from . import forecast_fx_rate
from . import forecast_customer_term
from . import forecast_config
```

**Step 3: Create the config view** — copy from scaffold and add two new tabs

The scaffold's `forecast_config_views.xml` has FX Rates and Customer Terms tabs. Add:
- A **Supplier Payment Terms** tab (new)
- `tax_id` field in the Settings group

```bash
cp mml_financial_forecast/mml_financial_forecast/views/forecast_config_views.xml \
   mml_forecast_core/views/forecast_config_views.xml
```

Then open and add inside the notebook after the Customer Terms page:

```xml
<page string="Supplier Payment Terms" name="supplier_terms">
    <field name="supplier_term_ids">
        <list editable="bottom">
            <field name="supplier_id"/>
            <field name="deposit_pct"/>
            <field name="deposit_trigger_days"/>
            <field name="production_lead_days"/>
            <field name="origin_port_id"/>
            <field name="payment_method"/>
            <field name="notes"/>
        </list>
    </field>
</page>
```

And add `tax_id` to the Settings group next to `freight_rate_cbm`:
```xml
<field name="tax_id"/>
```

**Step 4: Add security rows**

```csv
access_forecast_config_user,forecast.config user,model_forecast_config,base.group_user,1,0,0,0
access_forecast_config_manager,forecast.config manager,model_forecast_config,base.group_system,1,1,1,1
```

**Step 5: Commit**

```bash
git add mml_forecast_core/
git commit -m "feat(core): add forecast.config with tax_id and supplier_term_ids"
```

---

### Task 1.7: Create the top-level Forecasting menu

**Files:**
- Create: `mml_forecast_core/views/menu_views.xml`

**Step 1: Write the menu**

```xml
<!-- mml_forecast_core/views/menu_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Root Forecasting app — child modules hang their menus off this -->
    <menuitem id="menu_mml_forecasting_root"
              name="Forecasting"
              web_icon="mml_forecast_core,static/description/icon.png"
              sequence="45"/>

    <!-- Config menu lives in core — both demand and financial link to configs -->
    <menuitem id="menu_forecast_configs"
              name="Forecasts"
              parent="menu_mml_forecasting_root"
              sequence="5"/>

    <menuitem id="menu_forecast_config_all"
              name="All Forecasts"
              parent="menu_forecast_configs"
              action="action_forecast_config"
              sequence="10"/>

    <!-- Settings sub-menu -->
    <menuitem id="menu_forecast_settings"
              name="Configuration"
              parent="menu_mml_forecasting_root"
              sequence="90"/>

    <menuitem id="menu_forecast_origin_ports"
              name="Origin Ports"
              parent="menu_forecast_settings"
              action="action_forecast_origin_port"
              sequence="10"/>
</odoo>
```

**Step 2: Commit**

```bash
git add mml_forecast_core/views/menu_views.xml
git commit -m "feat(core): add top-level Forecasting app menu"
```

---

### Task 1.8: Install test for `mml_forecast_core`

**Files:**
- Create: `mml_forecast_core/tests/__init__.py`
- Create: `mml_forecast_core/tests/test_install.py`

**Step 1: Write the test**

```python
# mml_forecast_core/tests/test_install.py
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
            'code': 'CNSHA',
            'name': 'Shanghai',
            'transit_days_nz': 22,
        })
        self.assertEqual(port.transit_days_nz, 22)

    def test_forecast_config_has_tax_id_field(self):
        config = self.env['forecast.config'].new({
            'name': 'Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        self.assertIn('tax_id', config._fields)

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

    def test_customer_term_date_snapping(self):
        from datetime import date
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
        # Invoice Jan 15 → receipt = last day of Feb
        receipt = term.compute_receipt_date(date(2026, 1, 15))
        self.assertEqual(receipt, date(2026, 2, 28))
```

**Step 2: Run the test**

```bash
odoo-bin --test-enable -d dev -u mml_forecast_core \
  --test-tags /mml_forecast_core:TestCoreInstall
```
Expected: PASS

**Step 3: Commit**

```bash
git add mml_forecast_core/tests/
git commit -m "test(core): add install and model tests for mml_forecast_core"
```

---

## Sprint 2: `mml_forecast_demand`

**Goal:** Migrate `mml_roq_forecast` from `roq.model/` into `mml.forecasting/` as `mml_forecast_demand`. Update the manifest to depend on `mml_forecast_core`. Replace `roq.port` with `forecast.origin.port` from core. Expose the standard demand interface. Update menus to sit under the core's Forecasting root.

**Pre-condition:** Sprint 1 complete. `mml_forecast_core` installs cleanly.

---

### Task 2.1: Copy ROQ module into the forecasting repo

**Step 1: Copy the directory**

```bash
cp -r "E:\ClaudeCode\projects\mml.odoo.apps\roq.model\mml_roq_forecast" \
      "E:\ClaudeCode\projects\mml.odoo.apps\mml.forecasting\mml_forecast_demand"
```

**Step 2: Rename the directory**

The copy above names it `mml_forecast_demand`. Verify:

```bash
ls mml_forecast_demand/
# Expected: __init__.py __manifest__.py hooks.py models/ services/ views/ tests/ ...
```

**Step 3: Initial commit of the raw copy**

```bash
git add mml_forecast_demand/
git commit -m "feat(demand): initial copy of mml_roq_forecast → mml_forecast_demand"
```

> This commit preserves the original state before any refactoring. Makes diffs clean.

---

### Task 2.2: Update the manifest

**File:** `mml_forecast_demand/__manifest__.py`

**Step 1: Edit the manifest**

Key changes:
- `name`: `'MML Forecast Demand'`
- `depends`: add `'mml_forecast_core'`, remove `'mml_base'` (unless `mml_base` is available — check your stack; if not installed, remove it)
- `data`: remove `'data/roq_port_data.xml'` (ports now live in core)
- Keep all other data entries unchanged

```python
{
    'name': 'MML Forecast Demand',
    'version': '19.0.1.0.0',
    'summary': 'Demand forecasting, ROQ calculation, container consolidation, and 12-month procurement planning',
    'author': 'MML Consumer Products Ltd',
    'category': 'Forecasting',
    'depends': [
        'mml_forecast_core',
        'base', 'sale', 'purchase', 'stock',
        'stock_landed_costs',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        # 'data/roq_port_data.xml',  ← REMOVED: ports now in mml_forecast_core
        'data/ir_cron_data.xml',
        'views/roq_forecast_run_views.xml',
        'views/roq_forecast_line_views.xml',
        'views/roq_shipment_group_views.xml',
        'views/roq_raise_po_wizard_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/roq_order_dashboard_views.xml',
        'views/roq_shipment_calendar_views.xml',
        'views/roq_reschedule_wizard_views.xml',
        'views/stock_warehouse_views.xml',
        'views/menus.xml',
        'reports/supplier_order_schedule.xml',
        'reports/supplier_order_schedule_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mml_forecast_demand/static/src/scss/shipment_calendar.scss',
        ],
    },
    'external_dependencies': {'python': ['numpy', 'scipy']},
    'installable': True,
    'auto_install': False,
    'application': True,
    'web_icon': 'mml_forecast_demand,static/description/icon.png',
    'license': 'LGPL-3',
}
```

**Step 2: Commit**

```bash
git add mml_forecast_demand/__manifest__.py
git commit -m "feat(demand): update manifest — depends on mml_forecast_core, remove roq_port_data"
```

---

### Task 2.3: Migrate `roq.port` → `forecast.origin.port`

`roq.port` (in demand) and `forecast.origin.port` (in core) are the same concept. The sprint brief says to reuse the same records. Since `mml_forecast_demand` depends on `mml_forecast_core`, demand can reference `forecast.origin.port` directly.

**Strategy:**
1. Add `origin_port_id` (Many2one `forecast.origin.port`) to `res.partner` extension as the new field
2. Keep `fob_port` (Char) on `res.partner` for backwards compat — mark as deprecated in help text
3. Keep `roq.port` model but deprecate it — future cleanup task
4. Update `forward_plan_generator.py` to use `forecast.origin.port` for transit days when available

**File:** `mml_forecast_demand/models/res_partner_ext.py`

**Step 1: Add `origin_port_id` field** alongside existing `fob_port`

Open `mml_forecast_demand/models/res_partner_ext.py` and add:

```python
origin_port_id = fields.Many2one(
    'forecast.origin.port',
    string='Origin Port',
    help='Primary shipping port for this supplier. Used for transit time calculations.',
)
```

**Step 2: Update `forward_plan_generator.py`** — use `origin_port_id.transit_days_nz` when set

In `mml_forecast_demand/services/forward_plan_generator.py`, update the supplier FOB port lookup:

```python
# Prefer the structured origin_port_id if set; fall back to fob_port char field
def _get_transit_days(self, supplier):
    if supplier.origin_port_id:
        return supplier.origin_port_id.transit_days_nz
    return 22  # fallback default
```

**Step 3: Commit**

```bash
git add mml_forecast_demand/
git commit -m "feat(demand): add origin_port_id on res.partner linking to forecast.origin.port"
```

---

### Task 2.4: Update menus to sit under the core root

**File:** `mml_forecast_demand/views/menus.xml`

The ROQ module currently defines its own root menu (`ROQ Forecast` or similar). Change the demand menu to be a child of `mml_forecast_core.menu_mml_forecasting_root`.

**Step 1: Edit `menus.xml`** — replace the root menuitem with a child menuitem

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Demand Planning sits under the shared Forecasting root from mml_forecast_core -->
    <menuitem id="menu_demand_planning"
              name="Demand Planning"
              parent="mml_forecast_core.menu_mml_forecasting_root"
              sequence="20"/>

    <menuitem id="menu_roq_dashboard"
              name="ROQ Dashboard"
              parent="menu_demand_planning"
              action="action_roq_order_dashboard"
              sequence="10"/>

    <menuitem id="menu_roq_forecast_runs"
              name="Forecast Runs"
              parent="menu_demand_planning"
              action="action_roq_forecast_run"
              sequence="20"/>

    <menuitem id="menu_roq_shipment_calendar"
              name="Shipment Calendar"
              parent="menu_demand_planning"
              action="action_roq_shipment_calendar"
              sequence="30"/>

    <menuitem id="menu_roq_forward_plans"
              name="Forward Plans"
              parent="menu_demand_planning"
              action="action_roq_forward_plan"
              sequence="40"/>
</odoo>
```

> Remove any `<menuitem>` that had no `parent=` (the old root menu). The new root is owned by core.

**Step 2: Commit**

```bash
git add mml_forecast_demand/views/menus.xml
git commit -m "feat(demand): move menus under mml_forecast_core root"
```

---

### Task 2.5: Expose the standard demand interface

The financial wizard needs to pull demand from ROQ when it's installed. Add a method to `roq.forecast.run` that returns the standard demand contract.

**File:** `mml_forecast_demand/models/roq_forecast_run.py`

**Step 1: Add the method**

Open `mml_forecast_demand/models/roq_forecast_run.py` and add:

```python
def get_demand_forecast(self, date_start, horizon_months):
    """
    Standard demand interface for mml_forecast_financial.

    Returns a list of dicts matching the financial wizard's demand contract:
    [
        {
            'product_id': int,
            'partner_id': int,        # 0 if not customer-specific
            'period_start': date,
            'period_label': str,      # '2026-04'
            'forecast_units': float,
            'brand': str,
            'category': str,
        },
        ...
    ]

    Maps roq.forecast.line weekly demand → monthly demand (× 4.33).
    Only includes lines where abc_tier != 'D' and forecasted_weekly_demand > 0.
    """
    from dateutil.relativedelta import relativedelta

    self.ensure_one()
    WEEKS_PER_MONTH = 4.33

    lines = self.env['roq.forecast.line'].search([
        ('run_id', '=', self.id),
        ('abc_tier', '!=', 'D'),
        ('forecasted_weekly_demand', '>', 0),
    ])

    demand = []
    for month_offset in range(horizon_months):
        period_start = (date_start + relativedelta(months=month_offset)).replace(day=1)
        period_label = period_start.strftime('%Y-%m')

        for line in lines:
            product = line.product_id
            tmpl = product.product_tmpl_id
            brand = (
                getattr(tmpl, 'x_brand', None) or
                (tmpl.categ_id.name if tmpl.categ_id else 'Unknown')
            )
            demand.append({
                'product_id': product.id,
                'partner_id': line.supplier_id.id if line.supplier_id else 0,
                'period_start': period_start,
                'period_label': period_label,
                'forecast_units': line.forecasted_weekly_demand * WEEKS_PER_MONTH,
                'brand': brand,
                'category': tmpl.categ_id.name if tmpl.categ_id else 'Uncategorised',
            })

    return demand
```

**Step 2: Write a test**

```python
# mml_forecast_demand/tests/test_demand_interface.py
from datetime import date
from odoo.tests.common import TransactionCase


class TestDemandInterface(TransactionCase):

    def setUp(self):
        super().setUp()
        self.run = self.env['roq.forecast.run'].create({'status': 'complete'})
        self.product = self.env['product.product'].create({
            'name': 'Interface Test SKU', 'type': 'product',
        })
        self.warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['roq.forecast.line'].create({
            'run_id': self.run.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse.id,
            'forecasted_weekly_demand': 10.0,
            'abc_tier': 'B',
        })

    def test_returns_list_of_dicts(self):
        demand = self.run.get_demand_forecast(date(2026, 4, 1), horizon_months=3)
        self.assertIsInstance(demand, list)
        self.assertGreater(len(demand), 0)

    def test_monthly_demand_is_weekly_times_4_33(self):
        demand = self.run.get_demand_forecast(date(2026, 4, 1), horizon_months=1)
        entry = next(d for d in demand if d['product_id'] == self.product.id)
        self.assertAlmostEqual(entry['forecast_units'], 10.0 * 4.33, places=1)

    def test_returns_correct_number_of_months(self):
        demand = self.run.get_demand_forecast(date(2026, 4, 1), horizon_months=6)
        months = set(d['period_label'] for d in demand if d['product_id'] == self.product.id)
        self.assertEqual(len(months), 6)

    def test_tier_d_excluded(self):
        self.env['roq.forecast.line'].create({
            'run_id': self.run.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse.id,
            'forecasted_weekly_demand': 5.0,
            'abc_tier': 'D',
        })
        demand = self.run.get_demand_forecast(date(2026, 4, 1), horizon_months=1)
        # Only B-tier line should appear, not D
        entries = [d for d in demand if d['product_id'] == self.product.id]
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0]['forecast_units'], 10.0 * 4.33, places=1)
```

**Step 3: Run tests**

```bash
odoo-bin --test-enable -d dev -u mml_forecast_demand \
  --test-tags /mml_forecast_demand:TestDemandInterface
```
Expected: PASS

**Step 4: Run the full existing test suite** — confirm nothing broke

```bash
odoo-bin --test-enable -d dev -u mml_forecast_demand \
  --test-tags mml_forecast_demand
```
Expected: All PASS

**Step 5: Commit**

```bash
git add mml_forecast_demand/
git commit -m "feat(demand): expose get_demand_forecast() standard interface on roq.forecast.run"
```

---

## Sprint 3: `mml_forecast_financial`

**Goal:** Create `mml_forecast_financial/` at the repo root from the scaffold. Remove models now in core (`forecast.config`, `forecast.fx.rate`, `forecast.customer.term`). Update manifest to depend on `mml_forecast_core`. Update menus. Wire the ROQ demand source. Delete the old double-nested `mml_financial_forecast/` folder.

**Pre-condition:** Sprints 1 and 2 complete.

---

### Task 3.1: Create `mml_forecast_financial` module scaffold

**Step 1: Create the directory structure**

```bash
mkdir -p mml_forecast_financial/models
mkdir -p mml_forecast_financial/wizard
mkdir -p mml_forecast_financial/views
mkdir -p mml_forecast_financial/security
mkdir -p mml_forecast_financial/tests
mkdir -p mml_forecast_financial/static/description
```

**Step 2: Write the manifest**

```python
# mml_forecast_financial/__manifest__.py
{
    'name': 'MML Forecast Financial',
    'version': '19.0.1.0.0',
    'summary': 'P&L, cash flow, and scenario planning from demand forecasts',
    'author': 'MML Consumer Products Ltd',
    'category': 'Forecasting',
    'depends': [
        'mml_forecast_core',
        'sale',
        'purchase',
        'account',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/forecast_opex_views.xml',
        'views/forecast_summary_views.xml',
        'views/menu_views.xml',
        'wizard/forecast_generate_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'web_icon': 'mml_forecast_financial,static/description/icon.png',
    'license': 'LGPL-3',
}
```

> No `mml_forecast_demand` in depends — it's an optional soft dependency checked at runtime via `self.env.get()`.

**Step 3: Create `__init__.py`**

```python
# mml_forecast_financial/__init__.py
from . import models
from . import wizard
```

```python
# mml_forecast_financial/models/__init__.py
from . import forecast_opex_line
from . import forecast_revenue_line
from . import forecast_cogs_line
from . import forecast_pnl_line
from . import forecast_cashflow_line
```

```python
# mml_forecast_financial/wizard/__init__.py
from . import forecast_generate_wizard
```

**Step 4: Commit the scaffold**

```bash
git add mml_forecast_financial/
git commit -m "feat(financial): scaffold mml_forecast_financial module"
```

---

### Task 3.2: Copy line models from scaffold

These five models are unchanged from the scaffold. Copy them directly.

**Step 1: Copy files**

```bash
SRC="mml_financial_forecast/mml_financial_forecast/models"
DST="mml_forecast_financial/models"

cp $SRC/forecast_opex_line.py    $DST/
cp $SRC/forecast_revenue_line.py $DST/
cp $SRC/forecast_cogs_line.py    $DST/
cp $SRC/forecast_pnl_line.py     $DST/
cp $SRC/forecast_cashflow_line.py $DST/
```

**Step 2: Copy views**

```bash
SRC="mml_financial_forecast/mml_financial_forecast/views"
DST="mml_forecast_financial/views"

cp $SRC/forecast_opex_views.xml    $DST/
cp $SRC/forecast_summary_views.xml $DST/
```

**Step 3: Copy wizard view**

```bash
cp mml_financial_forecast/mml_financial_forecast/wizard/forecast_generate_views.xml \
   mml_forecast_financial/wizard/
```

**Step 4: Copy security**

```bash
cp mml_financial_forecast/mml_financial_forecast/security/ir.model.access.csv \
   mml_forecast_financial/security/
```

Remove the rows for `forecast.config`, `forecast.fx.rate`, `forecast.customer.term` — those are now in core's security file.

**Step 5: Commit**

```bash
git add mml_forecast_financial/
git commit -m "feat(financial): copy line models and views from scaffold"
```

---

### Task 3.3: Copy and update the wizard

The wizard is mostly copied as-is. Two changes:
1. Uncomment and wire the ROQ demand path using `self.env.get()`
2. Replace hardcoded `cif * 0.15` with `config.tax_id` lookup

**File:** Copy `mml_financial_forecast/mml_financial_forecast/wizard/forecast_generate_wizard.py` → `mml_forecast_financial/wizard/forecast_generate_wizard.py`

Then make these two targeted edits:

**Edit 1 — Demand source logic** (around line 87–95 in original):

```python
def _get_demand_forecast(self, config, months):
    # --- Strategy 1: ROQ module (mml_forecast_demand) if installed ---
    ForecastRun = self.env.get('roq.forecast.run')
    if ForecastRun:
        latest_run = ForecastRun.search(
            [('status', '=', 'complete')],
            order='create_date desc',
            limit=1,
        )
        if latest_run:
            return latest_run.get_demand_forecast(config.date_start, config.horizon_months)

    # --- Strategy 2: Trailing sale history fallback ---
    return self._demand_from_sale_history(config, months)
```

**Edit 2 — Import tax lookup** (in `_generate_cashflow_lines`, replace `cif * 0.15`):

```python
# Replace:
gst_on_import = cif * 0.15

# With:
tax_rate = (config.tax_id.amount / 100.0) if config.tax_id else 0.0
gst_on_import = cif * tax_rate
```

**Commit**

```bash
git add mml_forecast_financial/wizard/forecast_generate_wizard.py
git commit -m "feat(financial): wire ROQ demand source + dynamic tax rate from config.tax_id"
```

---

### Task 3.4: Create the Financial Planning menu

**File:** `mml_forecast_financial/views/menu_views.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_financial_planning"
              name="Financial Planning"
              parent="mml_forecast_core.menu_mml_forecasting_root"
              sequence="30"/>

    <menuitem id="menu_forecast_pnl"
              name="P&amp;L Summary"
              parent="menu_financial_planning"
              action="action_forecast_pnl"
              sequence="10"/>

    <menuitem id="menu_forecast_cashflow"
              name="Cash Flow"
              parent="menu_financial_planning"
              action="action_forecast_cashflow"
              sequence="20"/>

    <menuitem id="menu_forecast_revenue"
              name="Revenue Detail"
              parent="menu_financial_planning"
              action="action_forecast_revenue"
              sequence="30"/>

    <menuitem id="menu_forecast_cogs"
              name="COGS Detail"
              parent="menu_financial_planning"
              action="action_forecast_cogs"
              sequence="40"/>
</odoo>
```

**Commit**

```bash
git add mml_forecast_financial/views/menu_views.xml
git commit -m "feat(financial): add Financial Planning menu under core root"
```

---

### Task 3.5: Install test for `mml_forecast_financial`

```python
# mml_forecast_financial/tests/test_install.py
from odoo.tests.common import TransactionCase


class TestFinancialInstall(TransactionCase):

    def test_models_exist(self):
        self.assertTrue(self.env['forecast.opex.line'])
        self.assertTrue(self.env['forecast.revenue.line'])
        self.assertTrue(self.env['forecast.cogs.line'])
        self.assertTrue(self.env['forecast.pnl.line'])
        self.assertTrue(self.env['forecast.cashflow.line'])

    def test_wizard_exists(self):
        self.assertTrue(self.env['forecast.generate.wizard'])

    def test_config_has_tax_id(self):
        """tax_id field defined in core, accessible from financial context."""
        config = self.env['forecast.config'].new({
            'name': 'Financial Test',
            'date_start': '2026-01-01',
            'horizon_months': 12,
        })
        self.assertIn('tax_id', config._fields)

    def test_demand_fallback_when_roq_not_installed(self):
        """When mml_forecast_demand is not installed, wizard falls back to sale history."""
        config = self.env['forecast.config'].create({
            'name': 'Fallback Test',
            'date_start': '2026-01-01',
            'horizon_months': 3,
        })
        wizard = self.env['forecast.generate.wizard']
        months = wizard._build_month_buckets(config)
        # Should not raise — falls back gracefully to sale history
        demand = wizard._get_demand_forecast(config, months)
        self.assertIsInstance(demand, list)
```

**Run:**

```bash
odoo-bin --test-enable -d dev -u mml_forecast_financial \
  --test-tags /mml_forecast_financial:TestFinancialInstall
```

**Commit**

```bash
git add mml_forecast_financial/tests/
git commit -m "test(financial): add install tests for mml_forecast_financial"
```

---

### Task 3.6: Delete the old scaffold

**Step 1: Confirm new modules are working**

```bash
odoo-bin --test-enable -d dev \
  -u mml_forecast_core,mml_forecast_demand,mml_forecast_financial \
  --test-tags mml_forecast_core,mml_forecast_financial
```
Expected: All PASS

**Step 2: Delete the old double-nested folder**

```bash
rm -rf mml_financial_forecast/
```

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete mml_financial_forecast scaffold (replaced by three-module suite)"
```

---

## Sprint 4: Cashflow Rewrite

**Goal:** Rewrite `_generate_cashflow_lines()` in `mml_forecast_financial/wizard/forecast_generate_wizard.py` to implement the full supplier payment timing model. Outflows are placed in the correct months by back-calculating PO dates from sale months using `forecast.supplier.term` data (deposit %, production lead, port transit days).

**Pre-condition:** Sprints 1–3 complete. `forecast.supplier.term` and `forecast.origin.port` exist in core.

**The timing model to implement:**

```
For each sale month (from cogs lines):
  po_date = sale_month_start - total_lead_days - 14 (buffer)

  Deposit outflow:   po_date + deposit_trigger_days       → FOB × deposit_pct%
  Balance outflow:   po_date + total_lead_days (arrival)  → FOB × (1 - deposit_pct%)
  Freight outflow:   arrival_date                         → freight_total_nzd
  Duty outflow:      arrival_date + 20 working days        → duty_total_nzd + (CIF × tax_rate)

total_lead_days = production_lead_days + transit_days_nz
```

---

### Task 4.1: Write tests for the cashflow timing logic

**File:** `mml_forecast_financial/tests/test_cashflow_timing.py`

**Step 1: Write tests**

```python
# mml_forecast_financial/tests/test_cashflow_timing.py
from datetime import date
from odoo.tests.common import TransactionCase


class TestCashflowTiming(TransactionCase):
    """
    Tests for the supplier payment timing model in _generate_cashflow_lines().

    Key scenario: Shanghai supplier, 30% deposit, 45-day production, 22-day transit.
    Sale month: July 2026.
    Total lead: 67 days → PO placed ~late April.

    Expected outflows:
      Deposit (30%):  ~late April
      Balance (70%):  ~early July (arrival)
      Freight:        ~early July (arrival)
      Duty + GST:     ~late July (arrival + 20 working days)
    Expected inflow:
      Customer receipt: depends on customer term (tested separately)
    """

    def setUp(self):
        super().setUp()
        self.port = self.env['forecast.origin.port'].create({
            'code': 'CNSHA', 'name': 'Shanghai', 'transit_days_nz': 22,
        })
        self.supplier = self.env['res.partner'].create({
            'name': 'Shanghai Factory', 'supplier_rank': 1,
        })
        self.config = self.env['forecast.config'].create({
            'name': 'Cashflow Test',
            'date_start': date(2026, 7, 1),
            'horizon_months': 6,
            'freight_rate_cbm': 100.0,
        })
        self.term = self.env['forecast.supplier.term'].create({
            'config_id': self.config.id,
            'supplier_id': self.supplier.id,
            'deposit_pct': 30.0,
            'deposit_trigger_days': 0,
            'production_lead_days': 45,
            'origin_port_id': self.port.id,
        })

    def test_deposit_lands_before_sale_month(self):
        """30% deposit should appear months before the sale month."""
        wizard = self.env['forecast.generate.wizard']
        sale_month = date(2026, 7, 1)
        deposit_date = wizard._compute_deposit_date(self.term, sale_month)
        # Deposit must be before the sale month
        self.assertLess(deposit_date, sale_month)
        # Should be approximately late April (67 days before July + buffer)
        self.assertLessEqual(deposit_date.month, 5)  # April or May

    def test_balance_lands_at_arrival(self):
        """70% balance should land in the arrival month (same as sale month for short lead)."""
        wizard = self.env['forecast.generate.wizard']
        sale_month = date(2026, 7, 1)
        arrival_date = wizard._compute_arrival_date(self.term, sale_month)
        # Arrival should be in or around the sale month
        self.assertGreaterEqual(arrival_date.month, 6)
        self.assertLessEqual(arrival_date.month, 8)

    def test_duty_lands_after_arrival(self):
        """Duty + GST should land ~20 working days after arrival."""
        wizard = self.env['forecast.generate.wizard']
        sale_month = date(2026, 7, 1)
        arrival_date = wizard._compute_arrival_date(self.term, sale_month)
        duty_date = wizard._compute_duty_date(arrival_date)
        diff = (duty_date - arrival_date).days
        # 20 working days ≈ 28 calendar days
        self.assertGreaterEqual(diff, 25)
        self.assertLessEqual(diff, 35)

    def test_no_deposit_supplier_single_payment(self):
        """0% deposit — full payment at arrival, no deposit outflow."""
        self.term.deposit_pct = 0.0
        wizard = self.env['forecast.generate.wizard']
        sale_month = date(2026, 7, 1)
        deposit_date = wizard._compute_deposit_date(self.term, sale_month)
        # With 0% deposit, deposit date = arrival date (no separate payment)
        arrival_date = wizard._compute_arrival_date(self.term, sale_month)
        self.assertEqual(deposit_date, arrival_date)

    def test_full_generation_produces_outflows_in_correct_months(self):
        """
        End-to-end: generate a forecast for a single product, confirm outflows
        appear in months before the sale month.
        """
        product = self.env['product.product'].create({
            'name': 'Cashflow SKU', 'type': 'product', 'list_price': 50.0,
        })
        # Minimal cogs line for July 2026
        self.env['forecast.cogs.line'].create({
            'config_id': self.config.id,
            'period_start': date(2026, 7, 1),
            'period_label': '2026-07',
            'product_id': product.id,
            'forecast_units': 100,
            'fob_unit_fcy': 10.0,
            'fob_unit_nzd': 16.67,
            'fob_total_nzd': 1667.0,
            'freight_total_nzd': 50.0,
            'duty_total_nzd': 83.35,
            'tpl_total_nzd': 30.0,
            'fob_currency': 'USD',
        })
        wizard = self.env['forecast.generate.wizard']
        months = wizard._build_month_buckets(self.config)
        cogs_lines = self.config.cogs_line_ids
        rev_lines = self.env['forecast.revenue.line']  # empty ok for this test
        wizard._generate_cashflow_lines(self.config, months, rev_lines, cogs_lines)

        cf_lines = self.config.cashflow_line_ids
        self.assertGreater(len(cf_lines), 0)

        # Deposit should appear in a month before July
        deposit_months = cf_lines.filtered(
            lambda l: l.payments_fob > 0 and l.period_start < date(2026, 7, 1)
        )
        self.assertGreater(len(deposit_months), 0, "Deposit should appear before sale month")
```

**Step 2: Run — expect FAIL** (helper methods don't exist yet)

```bash
odoo-bin --test-enable -d dev --test-tags /mml_forecast_financial:TestCashflowTiming
```
Expected: AttributeError — `_compute_deposit_date` not found.

**Step 3: Commit failing tests**

```bash
git add mml_forecast_financial/tests/test_cashflow_timing.py
git commit -m "test(financial): add failing cashflow timing tests — TDD baseline"
```

---

### Task 4.2: Implement the cashflow rewrite

**File:** `mml_forecast_financial/wizard/forecast_generate_wizard.py`

Replace the `_generate_cashflow_lines()` method and add three helper methods. The rest of the wizard is unchanged.

**Step 1: Add helper methods** (add these after `_get_supplier_info` method):

```python
# -------------------------------------------------------------------------
# Cashflow timing helpers
# -------------------------------------------------------------------------

def _get_supplier_term(self, config, product):
    """
    Find the forecast.supplier.term for the primary supplier of this product.
    Returns None if no matching term configured.
    """
    supplier_info = product.seller_ids.sorted('sequence')[:1]
    if not supplier_info:
        return None
    return config.supplier_term_ids.filtered(
        lambda t: t.supplier_id == supplier_info.partner_id
    )[:1] or None

def _compute_po_date(self, term, sale_month_start):
    """
    Back-calculate the PO placement date from the sale month.

    po_date = sale_month_start - total_lead_days - 14 (buffer weeks)

    The 14-day buffer accounts for order preparation time and ensures
    stock arrives slightly before the sale month begins.
    """
    from datetime import timedelta
    total_lead = (
        term.total_lead_days if term
        else 67  # fallback: 45 production + 22 transit
    )
    return sale_month_start - timedelta(days=total_lead + 14)

def _compute_deposit_date(self, term, sale_month_start):
    """Date the deposit payment is due."""
    from datetime import timedelta
    if not term or term.deposit_pct == 0:
        return self._compute_arrival_date(term, sale_month_start)
    po_date = self._compute_po_date(term, sale_month_start)
    return po_date + timedelta(days=term.deposit_trigger_days)

def _compute_arrival_date(self, term, sale_month_start):
    """
    Date cargo arrives at NZ port.
    arrival = po_date + production_lead_days + transit_days_nz
    """
    from datetime import timedelta
    po_date = self._compute_po_date(term, sale_month_start)
    total_lead = term.total_lead_days if term else 67
    return po_date + timedelta(days=total_lead)

def _compute_duty_date(self, arrival_date):
    """
    Duty + import tax due approximately 20 working days after arrival.
    Approximated as 28 calendar days (20 working days × 1.4).
    """
    from datetime import timedelta
    return arrival_date + timedelta(days=28)

def _date_to_month_start(self, d):
    """Snap a date to the first of its month."""
    return d.replace(day=1)
```

**Step 2: Replace `_generate_cashflow_lines()`**

```python
def _generate_cashflow_lines(self, config, months, revenue_lines, cogs_lines):
    """
    Build monthly cash flow from timing rules.

    Receivables: Revenue shifted to receipt month per customer payment terms.
    Payables: COGS outflows placed in the correct months using supplier payment
              timing (deposit → balance → freight → duty), back-calculated from
              sale month via production lead + transit days.
    """
    from collections import defaultdict
    CashflowLine = self.env['forecast.cashflow.line']
    CustomerTerm = self.env['forecast.customer.term']

    month_map = {m[0]: m[1] for m in months}
    tax_rate = (config.tax_id.amount / 100.0) if config.tax_id else 0.0

    # --- Receivables: bucket by receipt month ---
    receipts_by_month = defaultdict(float)
    for rev in revenue_lines:
        receipt_date = CustomerTerm.get_default_receipt_date(
            config, rev.partner_id.id, rev.period_start,
        )
        receipt_month = self._date_to_month_start(receipt_date)
        if receipt_month in month_map:
            receipts_by_month[receipt_month] += rev.revenue

    # --- Payables: supplier timing model ---
    # Each category bucketed separately so the UI can show the waterfall
    fob_deposit_by_month = defaultdict(float)
    fob_balance_by_month = defaultdict(float)
    freight_by_month = defaultdict(float)
    duty_by_month = defaultdict(float)
    tpl_by_month = defaultdict(float)

    for cogs in cogs_lines:
        product = cogs.product_id
        sale_month = cogs.period_start
        term = self._get_supplier_term(config, product)

        # Deposit
        deposit_date = self._compute_deposit_date(term, sale_month)
        deposit_month = self._date_to_month_start(deposit_date)
        deposit_pct = term.deposit_pct / 100.0 if term else 0.3
        fob_deposit_by_month[deposit_month] += cogs.fob_total_nzd * deposit_pct

        # Balance (paid on arrival at NZ port)
        arrival_date = self._compute_arrival_date(term, sale_month)
        arrival_month = self._date_to_month_start(arrival_date)
        fob_balance_by_month[arrival_month] += cogs.fob_total_nzd * (1.0 - deposit_pct)

        # Freight (paid on delivery to port)
        freight_by_month[arrival_month] += cogs.freight_total_nzd

        # Duty + import tax (~20 working days post-arrival)
        duty_date = self._compute_duty_date(arrival_date)
        duty_month = self._date_to_month_start(duty_date)
        cif = cogs.fob_total_nzd + cogs.freight_total_nzd
        duty_by_month[duty_month] += cogs.duty_total_nzd + (cif * tax_rate)

        # 3PL (same month as sale — pick/pack on despatch)
        tpl_by_month[sale_month] += cogs.tpl_total_nzd

    # --- OpEx (fixed monthly, same month) ---
    opex_fixed = sum(
        line.monthly_amount or 0.0
        for line in config.opex_line_ids
        if line.cost_type == 'fixed'
    )

    # --- Build cashflow lines ---
    lines_data = []
    for period_start, period_label in months:
        month_rev = sum(r.revenue for r in revenue_lines if r.period_start == period_start)
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
            'payments_fob': (
                fob_deposit_by_month.get(period_start, 0.0)
                + fob_balance_by_month.get(period_start, 0.0)
            ),
            'payments_freight': freight_by_month.get(period_start, 0.0),
            'payments_duty_gst': duty_by_month.get(period_start, 0.0),
            'payments_3pl': tpl_by_month.get(period_start, 0.0),
            'payments_opex': opex_fixed + opex_var,
        })

    lines = CashflowLine.create(lines_data)
    cumulative = 0.0
    for line in lines.sorted('period_start'):
        cumulative += line.net_cashflow
        line.cumulative_cashflow = cumulative

    return lines
```

**Step 3: Run the cashflow tests**

```bash
odoo-bin --test-enable -d dev -u mml_forecast_financial \
  --test-tags /mml_forecast_financial:TestCashflowTiming
```
Expected: All PASS

**Step 4: Run full financial test suite**

```bash
odoo-bin --test-enable -d dev \
  --test-tags mml_forecast_core,mml_forecast_demand,mml_forecast_financial
```
Expected: All PASS

**Step 5: Commit**

```bash
git add mml_forecast_financial/wizard/forecast_generate_wizard.py \
        mml_forecast_financial/tests/test_cashflow_timing.py
git commit -m "feat(financial): rewrite cashflow engine with supplier payment timing model"
```

---

## Sprint 4 Verification Checklist

Before marking complete, verify manually in the UI:

- [ ] "Forecasting" appears as a single home screen tile
- [ ] "Demand Planning" sub-menu shows ROQ dashboard, runs, calendar
- [ ] "Financial Planning" sub-menu shows P&L, cashflow, revenue, COGS
- [ ] Create a forecast config → FX Rates, Supplier Terms, Customer Terms tabs all present
- [ ] `tax_id` field visible on config form
- [ ] Generate a forecast → P&L lines created, cashflow lines created
- [ ] Cashflow: deposit appears in months **before** sale month for a Shanghai supplier with 45-day production
- [ ] Cashflow: duty appears in month **after** arrival month
- [ ] If `mml_forecast_demand` installed: ROQ demand path is used (check logs for "demand from ROQ")
- [ ] If `mml_forecast_demand` NOT installed: falls back to sale history (check logs)
- [ ] `roq.model/` repo: archive on GitHub after all tests pass

---

## Repo Cleanup (After Sprint 4)

**Step 1: Archive `roq.model/` on GitHub**

Go to `https://github.com/JonaldM/<roq-repo-name>` → Settings → Danger Zone → Archive this repository.

This makes it read-only. History is preserved. No new commits can be pushed. Correct action — don't delete it.

**Step 2: No other repo changes needed.** `mml.forecasting` is the single source of truth.
