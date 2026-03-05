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

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.code} — {rec.name}'
