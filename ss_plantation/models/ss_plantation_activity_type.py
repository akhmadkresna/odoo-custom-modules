from odoo import fields, models


class SsPlantationActivityType(models.Model):
    _name = 'ss.plantation.activity.type'
    _description = 'Plantation Activity Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    uom_basis = fields.Selection(
        [('ha', "Hectare"), ('palm', "Palm"), ('none', "None")], default='ha', required=True)
    requires_inputs = fields.Boolean(string="Uses Stock Inputs")
