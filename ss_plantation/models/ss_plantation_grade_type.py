from odoo import fields, models


class SsPlantationGradeType(models.Model):
    _name = 'ss.plantation.grade.type'
    _description = 'Plantation FFB Grade Deduction Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    default_percent = fields.Float(string="Default Deduction (%)")
