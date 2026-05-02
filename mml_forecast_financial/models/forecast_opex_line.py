from odoo import models, fields


class ForecastOpexLine(models.Model):
    _name = 'forecast.opex.line'
    _description = 'Forecast Operating Expense Line'
    _order = 'cost_type, sequence'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='config_id.company_id.currency_id',
        store=True,
        string='Currency',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Expense Name', required=True)
    cost_type = fields.Selection([
        ('fixed', 'Fixed ($/month)'),
        ('variable', 'Variable (% of Revenue)'),
    ], string='Type', required=True, default='fixed')

    # Fixed cost fields
    monthly_amount = fields.Monetary(
        string='Monthly Amount (NZD)',
        currency_field='currency_id',
        help='For fixed costs: amount per month.',
    )

    # Variable cost fields
    pct_of_revenue = fields.Float(
        string='% of Revenue',
        digits=(5, 2),
        help='For variable costs: percentage of gross revenue. E.g. 3.5 for 3.5%.',
    )

    # Optional scoping
    brand = fields.Selection([
        ('all', 'All Brands'),
        ('volere', 'Volere'),
        ('annabel_langbein', 'Annabel Langbein'),
        ('enkel', 'Enkel'),
        ('enduro', 'Enduro'),
        ('rufus_coco', 'Rufus & Coco'),
    ], default='all', string='Brand Scope')

    notes = fields.Char(string='Notes')

    def compute_monthly_opex(self, monthly_revenue):
        """Return the NZD cost for a given month's revenue."""
        self.ensure_one()
        if self.cost_type == 'fixed':
            return self.monthly_amount or 0.0
        elif self.cost_type == 'variable':
            return monthly_revenue * (self.pct_of_revenue / 100.0)
        return 0.0
