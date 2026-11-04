from odoo import api, fields, models

from ..tools import geo


class SsPlantationLandmark(models.Model):
    _name = 'ss.plantation.landmark'
    _inherit = ['ss.plantation.geo.mixin']
    _description = 'Plantation Landmark'
    _order = 'type_id, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    type_id = fields.Many2one('ss.plantation.landmark.type', required=True, index=True)
    geometry_kind = fields.Selection(related='type_id.geometry_kind')
    estate_id = fields.Many2one('ss.plantation.estate', index=True, check_company=True)
    division_id = fields.Many2one(
        'ss.plantation.division', index=True, check_company=True,
        domain="[('estate_id', '=?', estate_id)]")
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    geometry_geojson = fields.Text(string="Geometry (GeoJSON)")
    latitude = fields.Float(compute='_compute_centre', store=True, readonly=False, digits=(10, 7))
    longitude = fields.Float(compute='_compute_centre', store=True, readonly=False, digits=(10, 7))
    note = fields.Text()
    photo = fields.Image(max_width=1024, max_height=1024)

    @api.depends('geometry_geojson')
    def _compute_centre(self):
        for landmark in self:
            centre = geo.centroid(landmark._ss_geometry('geometry_geojson'))
            if centre:
                landmark.latitude, landmark.longitude = centre
            else:
                landmark.latitude = landmark.latitude or 0.0
                landmark.longitude = landmark.longitude or 0.0

    @api.constrains('geometry_geojson', 'type_id')
    def _check_geometry_geojson(self):
        for landmark in self:
            landmark._ss_check_geojson('geometry_geojson', landmark.type_id.geometry_kind)
