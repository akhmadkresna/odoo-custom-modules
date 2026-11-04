from odoo import Command, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    ss_harvest_pay_ids = fields.One2many(
        'ss.plantation.harvest.pay', 'payslip_id', string="Harvest Pay", readonly=True)

    def action_ss_add_harvest_pay(self):
        """Add the draft harvest pay of the slip's period as one input line."""
        rule = self.env.ref('ss_plantation.salary_rule_harvest_pay')
        for slip in self:
            if slip.state not in ('draft', 'verify'):
                raise UserError(self.env._("Harvest pay can only be added to a draft payslip."))
            pays = self.env['ss.plantation.harvest.pay'].search([
                ('employee_id', '=', slip.employee_id.id),
                ('state', '=', 'draft'),
                ('date_from', '>=', slip.date_from),
                ('date_to', '<=', slip.date_to),
            ])
            if not pays:
                raise UserError(self.env._(
                    "No draft harvest pay for %(employee)s in this period. "
                    "Compute it first from Plantation > Payroll.", employee=slip.employee_id.name))
            commands = [Command.delete(line.id) for line in slip.input_line_ids
                        if line.salary_rule_id == rule]
            commands.append(Command.create({
                'salary_rule_id': rule.id,
                'amount': sum(pays.mapped('amount')),
            }))
            slip.input_line_ids = commands
            pays.write({'state': 'posted', 'payslip_id': slip.id})
