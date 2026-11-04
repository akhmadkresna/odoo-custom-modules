from odoo import api, fields, models


class SsPlantationDivision(models.Model):
    _name = 'ss.plantation.division'
    _inherit = ['ss.plantation.geo.mixin']
    _description = 'Plantation Division'
    _order = 'estate_id, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char()
    active = fields.Boolean(default=True)
    estate_id = fields.Many2one(
        'ss.plantation.estate', required=True, index=True, ondelete='restrict',
        domain="[('company_id', 'in', allowed_company_ids)]")
    company_id = fields.Many2one(related='estate_id.company_id', store=True, index=True)
    manager_id = fields.Many2one('hr.employee', string="Manager", check_company=True)
    store_location_id = fields.Many2one(
        'stock.location', string="Input Store", domain="[('usage', '=', 'internal')]",
        check_company=True,
        help="Location the field inputs (fertiliser, chemicals) are taken from.")
    block_ids = fields.One2many('ss.plantation.block', 'division_id')
    block_count = fields.Integer(compute='_compute_block_count')
    area_ha = fields.Float(compute='_compute_area_ha', store=True, digits=(16, 2))
    boundary_geojson = fields.Text(string="Boundary (GeoJSON)")

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)', "The division code must be unique per company.")

    @api.depends('block_ids.area_ha', 'block_ids.active')
    def _compute_area_ha(self):
        for division in self:
            division.area_ha = sum(division.block_ids.filtered('active').mapped('area_ha'))

    def _compute_block_count(self):
        counts = dict(self.env['ss.plantation.block']._read_group(
            [('division_id', 'in', self.ids)], ['division_id'], ['__count']))
        for division in self:
            division.block_count = counts.get(division, 0)

    @api.constrains('boundary_geojson')
    def _check_boundary_geojson(self):
        self._ss_check_geojson('boundary_geojson', 'polygon')
