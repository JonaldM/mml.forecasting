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
    currency_id = fields.Many2one(
        'res.currency',
        related='config_id.company_id.currency_id',
        store=True,
        string='Currency',
    )
    period_start = fields.Date(string='Month Start', required=True)
    period_label = fields.Char(string='Period')

    # --- Inflows ---
    receipts_from_customers = fields.Monetary(
        string='Customer Receipts (NZD)',
        currency_field='currency_id',
        help='Revenue received this month based on payment term timing.',
    )
    import_gst_refund = fields.Monetary(
        string='Import GST Refund (NZD)',
        currency_field='currency_id',
        help='GST input tax credit recovered from IRD, approximately 2 months '
             'after the import GST was paid to NZ Customs.',
    )

    # --- Outflows ---
    payments_fob_deposit = fields.Monetary(
        string='FOB Deposit (NZD)',
        currency_field='currency_id',
        help='Deposit paid at PO placement (% of FOB, timed months before sale month).',
    )
    payments_fob_balance = fields.Monetary(
        string='FOB Balance (NZD)',
        currency_field='currency_id',
        help='Balance payment at bill of lading (remainder of FOB, timed by transit days).',
    )
    payments_fob = fields.Monetary(
        string='FOB Payments (NZD)',
        currency_field='currency_id',
        compute='_compute_payments_fob',
        store=True,
        help='Total FOB payments = deposit + balance.',
    )
    payments_freight = fields.Monetary(
        string='Freight Payments (NZD)',
        currency_field='currency_id',
    )
    payments_duty_gst = fields.Monetary(
        string='Duty & GST (NZD)',
        currency_field='currency_id',
        help='Customs duty and import GST on arrival.',
    )
    payments_3pl = fields.Monetary(
        string='3PL Payments (NZD)',
        currency_field='currency_id',
    )
    payments_opex = fields.Monetary(
        string='OpEx Payments (NZD)',
        currency_field='currency_id',
    )
    total_outflows = fields.Monetary(
        string='Total Outflows (NZD)',
        currency_field='currency_id',
        compute='_compute_cashflow',
        store=True,
    )

    # --- Net ---
    net_cashflow = fields.Monetary(
        string='Net Cash Flow (NZD)',
        currency_field='currency_id',
        compute='_compute_cashflow',
        store=True,
    )
    cumulative_cashflow = fields.Monetary(
        string='Cumulative Cash Position (NZD)',
        currency_field='currency_id',
        help='Running total — set opening balance on first period.',
    )
    opening_balance = fields.Monetary(
        string='Opening Balance (NZD)',
        currency_field='currency_id',
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
