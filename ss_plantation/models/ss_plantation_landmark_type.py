from odoo import fields, models


class SsPlantationLandmarkType(models.Model):
    _name = 'ss.plantation.landmark.type'
    _description = 'Plantation Landmark Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    geometry_kind = fields.Selection(
        [('point', "Point"), ('line', "Line"), ('area', "Area")], default='point', required=True)
    color = fields.Char(default="#3b6e3b", help="Colour used on the map (CSS hex).")
    icon = fields.Char(default="📍", help="Emoji or short text shown on the map marker.")
