from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError


class SsPlantationHarvestPay(models.Model):
    _name = 'ss.plantation.harvest.pay'
    _description = 'Plantation Harvest Pay'
    _order = 'date_from desc, employee_id'
    _check_company_auto = True

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, check_company=True, ondelete='restrict')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    scheme_id = fields.Many2one('ss.plantation.pay.scheme', required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    harvested_kg = fields.Float(digits=(16, 1))
    bonus_amount = fields.Monetary(currency_field='currency_id')
    penalty_amount = fields.Monetary(currency_field='currency_id')
    amount = fields.Monetary(
        compute='_compute_amount', store=True, currency_field='currency_id')
    state = fields.Selection(
        [('draft', "Draft"), ('posted', "Added to Payslip")], default='draft', index=True)
    payslip_id = fields.Many2one('hr.payslip', readonly=True, copy=False)

    @api.depends('bonus_amount', 'penalty_amount')
    def _compute_amount(self):
        for pay in self:
            pay.amount = max(pay.bonus_amount - pay.penalty_amount, 0.0)

    @api.model
    def _compute_values(self, employee, scheme, date_from, date_to):
        """Harvest figures of `employee` for the period under `scheme`."""
        lines = self.env['ss.plantation.harvest.tally.line'].search([
            ('harvester_id', '=', employee.id),
            ('tally_state', '=', 'confirmed'),
            ('tally_date', '>=', date_from),
            ('tally_date', '<=', date_to),
        ])
        kg_by_day = defaultdict(float)
        for line in lines:
            kg_by_day[line.tally_date] += line.est_weight_kg
        total_kg = sum(kg_by_day.values())
        rest_days = (
            self.env['ss.plantation.pay.scheme']._rest_days(employee, date_from, date_to)
            if scheme.holiday_factor != 1.0 else set())
        bonus = 0.0
        for day, kg in kg_by_day.items():
            factor = scheme.holiday_factor if day in rest_days else 1.0
            if scheme.mode == 'piece_rate':
                bonus += kg * scheme.rate_per_kg * factor
            elif scheme.mode == 'mixed':
                bonus += scheme._tiered_bonus(max(kg - scheme.basis_kg, 0.0)) * factor
        penalty = (
            sum(lines.mapped('bunches_unripe')) * scheme.penalty_unripe
            + sum(lines.mapped('loose_left_kg')) * scheme.penalty_loose_left)
        return {
            'employee_id': employee.id,
            'scheme_id': scheme.id,
            'company_id': scheme.company_id.id,
            'date_from': date_from,
            'date_to': date_to,
            'harvested_kg': total_kg,
            'bonus_amount': bonus,
            'penalty_amount': penalty,
        }

    @api.model
    def _generate(self, date_from, date_to, employees):
        """Create (or refresh) draft pay records; employees without a scheme are skipped."""
        if date_from > date_to:
            raise UserError(self.env._("The period start must not be after its end."))
        existing = self.search([
            ('employee_id', 'in', employees.ids), ('date_from', '=', date_from),
            ('date_to', '=', date_to), ('state', '=', 'draft')])
        existing.unlink()
        vals_list = [
            self._compute_values(employee, employee.ss_pay_scheme_id, date_from, date_to)
            for employee in employees if employee.ss_pay_scheme_id]
        return self.create(vals_list)
