from odoo import api, fields, models


class SsPlantationWeighGradeLine(models.Model):
    _name = 'ss.plantation.weigh.grade.line'
    _description = 'Plantation Weigh Ticket Grade Deduction'

    ticket_id = fields.Many2one(
        'ss.plantation.weigh.ticket', required=True, ondelete='cascade', index=True)
    grade_type_id = fields.Many2one('ss.plantation.grade.type', required=True)
    percent = fields.Float(string="Deduction (%)")
    kg = fields.Float(string="Deduction (kg)", digits=(16, 1))
    deduction_kg = fields.Float(compute='_compute_deduction_kg', store=True, digits=(16, 1))

    _one_basis = models.Constraint(
        'CHECK(percent >= 0 AND kg >= 0 AND (percent = 0 OR kg = 0))',
        "Give the deduction either as a percentage or in kg, not both.")

    @api.onchange('grade_type_id')
    def _onchange_grade_type_id(self):
        if self.grade_type_id and not self.kg:
            self.percent = self.grade_type_id.default_percent

    @api.depends('percent', 'kg', 'ticket_id.net_kg')
    def _compute_deduction_kg(self):
        for line in self:
            line.deduction_kg = line.kg or line.ticket_id.net_kg * line.percent / 100.0
