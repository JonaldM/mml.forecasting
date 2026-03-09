from odoo import models, fields, api, _
from odoo.exceptions import UserError
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

    # --- Import tax (replaces hardcoded 15% GST in cashflow wizard) ---
    tax_id = fields.Many2one(
        'account.tax',
        string='Import Tax',
        domain="[('type_tax_use', '=', 'purchase')]",
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

    def _compute_totals(self):
        # Base no-op — overridden by mml_forecast_financial which has access to pnl_line_ids
        for rec in self:
            rec.total_revenue = 0.0
            rec.total_cogs = 0.0
            rec.total_gross_margin = 0.0
            rec.gross_margin_pct = 0.0

    def action_generate_forecast(self):
        self.ensure_one()
        Wizard = self.env.get('forecast.generate.wizard')
        if Wizard is None:
            raise UserError(
                _("The MML Forecast Financial module must be installed to generate forecasts.")
            )
        Wizard.with_context(active_id=self.id).generate(self)
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
