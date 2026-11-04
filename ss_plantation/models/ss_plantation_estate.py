from odoo import api, fields, models


class SsPlantationEstate(models.Model):
    _name = 'ss.plantation.estate'
    _inherit = ['ss.plantation.geo.mixin']
    _description = 'Plantation Estate'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    division_ids = fields.One2many('ss.plantation.division', 'estate_id')
    division_count = fields.Integer(compute='_compute_division_count')
    boundary_geojson = fields.Text(string="Boundary (GeoJSON)")

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)', "The estate code must be unique per company.")

    @api.depends('division_ids')
    def _compute_division_count(self):
        counts = dict(self.env['ss.plantation.division']._read_group(
            [('estate_id', 'in', self.ids)], ['estate_id'], ['__count']))
        for estate in self:
            estate.division_count = counts.get(estate, 0)

    @api.constrains('boundary_geojson')
    def _check_boundary_geojson(self):
        self._ss_check_geojson('boundary_geojson', 'polygon')
