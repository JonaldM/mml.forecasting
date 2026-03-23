from odoo import models, fields, api


class ForecastCashflowLine(models.Model):
    _name = 'forecast.cashflow.line'
    _description = 'Forecast Cash Flow Line'
    _order = 'period_start'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # --- Inflows ---
    receipts_from_customers = fields.Float(
        string='Customer Receipts (NZD)',
        help='Revenue received this month based on payment term timing.',
    )
    import_gst_refund = fields.Float(
        string='Import GST Refund (NZD)',
        help='GST input tax credit recovered from IRD, approximately 2 months '
             'after the import GST was paid to NZ Customs.',
    )

    # --- Outflows ---
    payments_fob_deposit = fields.Float(
        string='FOB Deposit (NZD)',
        help='Deposit paid at PO placement (% of FOB, timed months before sale month).',
    )
    payments_fob_balance = fields.Float(
        string='FOB Balance (NZD)',
        help='Balance payment at bill of lading (remainder of FOB, timed by transit days).',
    )
    payments_fob = fields.Float(
        string='FOB Payments (NZD)',
        compute='_compute_payments_fob',
        store=True,
        help='Total FOB payments = deposit + balance.',
    )
    payments_freight = fields.Float(string='Freight Payments (NZD)')
    payments_duty_gst = fields.Float(
        string='Duty & GST (NZD)',
        help='Customs duty and import GST on arrival.',
    )
    payments_3pl = fields.Float(string='3PL Payments (NZD)')
    payments_opex = fields.Float(string='OpEx Payments (NZD)')
    total_outflows = fields.Float(
        string='Total Outflows (NZD)',
        compute='_compute_cashflow',
        store=True,
    )

    # --- Net ---
    net_cashflow = fields.Float(
        string='Net Cash Flow (NZD)',
        compute='_compute_cashflow',
        store=True,
    )
    cumulative_cashflow = fields.Float(
        string='Cumulative Cash Position (NZD)',
        help='Running total — set opening balance on first period.',
    )
    opening_balance = fields.Float(
        string='Opening Balance (NZD)',
        help='Set on the first period only; subsequent periods are computed.',
    )

    @api.depends('payments_fob_deposit', 'payments_fob_balance')
    def _compute_payments_fob(self):
        for rec in self:
            rec.payments_fob = rec.payments_fob_deposit + rec.payments_fob_balance

    @api.depends(
        'receipts_from_customers', 'import_gst_refund',
        'payments_fob_deposit', 'payments_fob_balance',
        'payments_freight', 'payments_duty_gst',
        'payments_3pl', 'payments_opex',
    )
    def _compute_cashflow(self):
        for rec in self:
            rec.total_outflows = (
                rec.payments_fob
                + rec.payments_freight
                + rec.payments_duty_gst
                + rec.payments_3pl
                + rec.payments_opex
            )
            total_inflows = rec.receipts_from_customers + rec.import_gst_refund
            rec.net_cashflow = total_inflows - rec.total_outflows
