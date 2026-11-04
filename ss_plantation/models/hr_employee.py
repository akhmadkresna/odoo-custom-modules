from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ss_pay_scheme_id = fields.Many2one(
        'ss.plantation.pay.scheme', string="Harvest Pay Scheme", groups='hr.group_hr_user',
        check_company=True)
