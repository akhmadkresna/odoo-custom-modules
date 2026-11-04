from odoo import fields, models
from odoo.exceptions import UserError


class SsPlantationHarvestPayWizard(models.TransientModel):
    _name = 'ss.plantation.harvest.pay.wizard'
    _description = 'Compute Harvest Pay'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    employee_ids = fields.Many2many(
        'hr.employee', string="Employees",
        help="Leave empty for every employee that has a pay scheme.")

    def action_compute(self):
        self.ensure_one()
        employees = self.employee_ids or self.env['hr.employee'].search(
            [('ss_pay_scheme_id', '!=', False)])
        pays = self.env['ss.plantation.harvest.pay']._generate(
            self.date_from, self.date_to, employees)
        if not pays:
            raise UserError(self.env._("No employee with a harvest pay scheme was found."))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Harvest Pay"),
            'res_model': 'ss.plantation.harvest.pay',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pays.ids)],
        }
