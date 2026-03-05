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
