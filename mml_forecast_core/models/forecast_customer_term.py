import calendar
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api


class ForecastCustomerTerm(models.Model):
    _name = 'forecast.customer.term'
    _description = 'Forecast Customer Payment Term'
    _order = 'partner_id'

    config_id = fields.Many2one(
        'forecast.config',
        string='Forecast',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
    )
    rule_type = fields.Selection([
        ('days_then_dom', 'N Days + Snap to Day-of-Month'),
        ('next_month_dom', 'Day-of-Month in Following Month'),
        ('end_of_following', 'Last Day of Following Month'),
    ], string='Rule Type', required=True, default='days_then_dom')

    buffer_days = fields.Integer(
        string='Buffer Days',
        default=45,
        help='For "days_then_dom": number of days from invoice before snapping.',
    )
    pay_day_of_month = fields.Integer(
        string='Pay Day of Month',
        default=20,
        help='Day of month payment lands. 0 or blank = last day.',
    )
    notes = fields.Char(string='Notes')

    def compute_receipt_date(self, invoice_date):
        """
        Given an invoice date, return the expected cash receipt date
        based on this customer's payment rule.

        Returns: date
        """
        self.ensure_one()

        if self.rule_type == 'days_then_dom':
            # Default rule: invoice_date + N days, then snap to next pay_day
            # E.g. invoice 1 Jan + 45 days = 15 Feb, snap to 20 Feb
            earliest = invoice_date + relativedelta(days=self.buffer_days)
            return self._snap_to_dom(earliest, self.pay_day_of_month)

        elif self.rule_type == 'next_month_dom':
            # Harvey Norman: 15th of the month following invoice
            next_month = invoice_date + relativedelta(months=1)
            dom = self.pay_day_of_month or 15
            max_day = calendar.monthrange(next_month.year, next_month.month)[1]
            return next_month.replace(day=min(dom, max_day))

        elif self.rule_type == 'end_of_following':
            # Briscoes: last calendar day of month following invoice
            next_month = invoice_date + relativedelta(months=1)
            last_day = calendar.monthrange(next_month.year, next_month.month)[1]
            return next_month.replace(day=last_day)

        # Fallback
        return invoice_date + relativedelta(days=45)

    @staticmethod
    def _snap_to_dom(ref_date, day_of_month):
        """
        Snap a reference date forward to the next occurrence of day_of_month.
        If ref_date is already past that day in the current month, roll to next month.
        """
        dom = day_of_month or 20
        max_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
        target_day = min(dom, max_day)

        if ref_date.day <= target_day:
            return ref_date.replace(day=target_day)
        else:
            # Roll to next month
            next_month = ref_date + relativedelta(months=1)
            max_day = calendar.monthrange(next_month.year, next_month.month)[1]
            return next_month.replace(day=min(dom, max_day))

    @api.model
    def get_default_receipt_date(self, config, partner_id, invoice_date):
        """
        Lookup the payment term for a given customer within a config.
        Falls back to default 45-day / 20th rule.
        """
        term = self.search([
            ('config_id', '=', config.id),
            ('partner_id', '=', partner_id),
        ], limit=1)
        if term:
            return term.compute_receipt_date(invoice_date)
        # Default: 45 days then snap to 20th
        earliest = invoice_date + relativedelta(days=45)
        return self._snap_to_dom(earliest, 20)
