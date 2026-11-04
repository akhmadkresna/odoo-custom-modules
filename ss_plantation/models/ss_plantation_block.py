from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import geo


class SsPlantationBlock(models.Model):
    _name = 'ss.plantation.block'
    _inherit = ['ss.plantation.geo.mixin']
    _description = 'Plantation Block'
    _order = 'division_id, code, name'
    _check_company_auto = True
    _rec_names_search = ['code', 'name']

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    division_id = fields.Many2one(
        'ss.plantation.division', required=True, index=True, ondelete='restrict',
        domain="[('company_id', 'in', allowed_company_ids)]")
    estate_id = fields.Many2one(related='division_id.estate_id', store=True, index=True)
    company_id = fields.Many2one(related='division_id.company_id', store=True, index=True)
    area_ha = fields.Float(required=True, digits=(16, 2))
    suggested_area_ha = fields.Float(
        compute='_compute_suggested_area_ha', digits=(16, 2),
        help="Area computed from the drawn boundary. Informational only.")
    planting_date = fields.Date()
    planting_year = fields.Integer(compute='_compute_planting_year', store=True)
    stand_count = fields.Integer(string="Palms")
    variety = fields.Char()
    avg_bunch_weight_kg = fields.Float(string="Avg Bunch Weight (kg)", digits=(16, 2))
    stage = fields.Selection(
        [('immature', "Immature (TBM)"), ('mature', "Mature (TM)"),
         ('replanting', "Replanting"), ('closed', "Closed")],
        default='immature', required=True, index=True)
    mature_date = fields.Date()
    last_harvest_date = fields.Date(readonly=True)
    boundary_geojson = fields.Text(string="Boundary (GeoJSON)")
    latitude = fields.Float(compute='_compute_centre', store=True, readonly=False, digits=(10, 7))
    longitude = fields.Float(compute='_compute_centre', store=True, readonly=False, digits=(10, 7))
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string="Cost Centre", readonly=True, copy=False, index=True)
    asset_id = fields.Many2one('account.asset', string="Mature Asset", readonly=True, copy=False)
    cost_total = fields.Float(
        string="Total Cost", compute='_compute_cost', digits='Product Price')
    cost_per_ha = fields.Float(compute='_compute_cost', digits='Product Price')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)', "The block code must be unique per company.")
    _area_positive = models.Constraint('CHECK(area_ha > 0)', "The block area must be positive.")

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for block in self:
            block.display_name = "%s - %s" % (block.code, block.name) if block.code else block.name

    @api.depends('planting_date')
    def _compute_planting_year(self):
        for block in self:
            block.planting_year = block.planting_date.year if block.planting_date else 0

    @api.depends('boundary_geojson')
    def _compute_suggested_area_ha(self):
        for block in self:
            block.suggested_area_ha = geo.area_ha(block._ss_geometry('boundary_geojson', 'polygon'))

    @api.depends('boundary_geojson')
    def _compute_centre(self):
        for block in self:
            centre = geo.centroid(block._ss_geometry('boundary_geojson', 'polygon'))
            if centre:
                block.latitude, block.longitude = centre
            else:
                block.latitude = block.latitude or 0.0
                block.longitude = block.longitude or 0.0

    @api.model
    def _analytic_column(self):
        """Name of the analytic line column that holds the block cost centre."""
        return self.env.ref('ss_plantation.analytic_plan_block')._column_name()

    def _compute_cost(self):
        column = self._analytic_column()
        rows = self.env['account.analytic.line']._read_group(
            [(column, 'in', self.analytic_account_id.ids)], [column], ['amount:sum'])
        totals = {account.id: -amount for account, amount in rows}
        for block in self:
            block.cost_total = totals.get(block.analytic_account_id.id, 0.0)
            block.cost_per_ha = block.cost_total / block.area_ha if block.area_ha else 0.0

    @api.constrains('boundary_geojson')
    def _check_boundary_geojson(self):
        self._ss_check_geojson('boundary_geojson', 'polygon')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('stage') == 'mature' and not vals.get('mature_date'):
                vals['mature_date'] = fields.Date.context_today(self)
        blocks = super().create(vals_list)
        blocks._create_analytic_account()
        return blocks

    def write(self, vals):
        if vals.get('stage') == 'mature' and 'mature_date' not in vals:
            for block in self.filtered(lambda b: not b.mature_date):
                block.mature_date = fields.Date.context_today(self)
        return super().write(vals)

    def _create_analytic_account(self):
        plan = self.env.ref('ss_plantation.analytic_plan_block')
        for block in self.filtered(lambda b: not b.analytic_account_id):
            block.analytic_account_id = self.env['account.analytic.account'].create({
                'name': "%s - %s" % (block.code, block.name),
                'plan_id': plan.id,
                'company_id': block.company_id.id,
            })

    def _has_history(self):
        self.ensure_one()
        if self.env['ss.plantation.activity'].search_count([('block_id', '=', self.id)], limit=1):
            return True
        return bool(self.analytic_account_id and self.env['account.analytic.line'].search_count(
            [(self._analytic_column(), '=', self.analytic_account_id.id)], limit=1))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_history(self):
        for block in self:
            if block._has_history():
                raise UserError(self.env._(
                    "Block %s has activities or costs. Archive it instead.", block.display_name))

    @api.model
    def get_map_data(self):
        """Everything the plantation map needs, limited to what the user may read."""
        since = fields.Date.context_today(self) - relativedelta(days=30)
        estates = self.env['ss.plantation.estate'].search_read(
            [('boundary_geojson', '!=', False)], ['name', 'boundary_geojson'])
        divisions = self.env['ss.plantation.division'].search_read(
            [('boundary_geojson', '!=', False)], ['name', 'estate_id', 'boundary_geojson'])
        blocks = self.search_read(
            [('boundary_geojson', '!=', False)],
            ['code', 'name', 'division_id', 'stage', 'area_ha', 'boundary_geojson',
             'last_harvest_date', 'latitude', 'longitude'])
        weights = {
            block.id: kg for block, kg in self.env['ss.plantation.harvest.tally.line']._read_group(
                [('block_id', 'in', [b['id'] for b in blocks]), ('tally_date', '>=', since),
                 ('tally_state', '=', 'confirmed')],
                ['block_id'], ['est_weight_kg:sum'])}
        for block in blocks:
            kg = weights.get(block['id'], 0.0)
            block['yield_kg_ha_30d'] = kg / block['area_ha'] if block['area_ha'] else 0.0
        landmarks = self.env['ss.plantation.landmark'].search_read(
            [('geometry_geojson', '!=', False)],
            ['name', 'type_id', 'geometry_geojson', 'note'])
        types = {
            t['id']: t for t in self.env['ss.plantation.landmark.type'].search_read(
                [], ['name', 'icon', 'color', 'geometry_kind'])}
        for landmark in landmarks:
            landmark['type'] = types.get(landmark['type_id'][0], {})
        return {
            'estates': estates, 'divisions': divisions, 'blocks': blocks,
            'landmarks': landmarks,
        }

    def action_set_mature(self):
        self.write({'stage': 'mature'})

    def action_view_cost(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Cost: %s", self.display_name),
            'res_model': 'account.analytic.line',
            'view_mode': 'list,pivot',
            'domain': [(self._analytic_column(), '=', self.analytic_account_id.id)],
        }

    def action_use_suggested_area(self):
        for block in self.filtered('suggested_area_ha'):
            block.area_ha = block.suggested_area_ha
