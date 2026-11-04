from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SsPlantationHarvestTallyLine(models.Model):
    _name = 'ss.plantation.harvest.tally.line'
    _description = 'Plantation Harvest Tally Line'
    _order = 'tally_id, block_id, id'
    _check_company_auto = True

    tally_id = fields.Many2one(
        'ss.plantation.harvest.tally', required=True, ondelete='cascade', index=True)
    tally_date = fields.Date(related='tally_id.date', store=True, index=True)
    tally_state = fields.Selection(related='tally_id.state', store=True)
    division_id = fields.Many2one(related='tally_id.division_id', store=True, index=True)
    company_id = fields.Many2one(related='tally_id.company_id', store=True, index=True)
    block_id = fields.Many2one(
        'ss.plantation.block', required=True, index=True, check_company=True,
        domain="[('division_id', '=', division_id), ('stage', '=', 'mature')]")
    harvester_id = fields.Many2one(
        'hr.employee', required=True, index=True, check_company=True)
    bunches_ripe = fields.Integer()
    bunches_unripe = fields.Integer()
    bunches_overripe = fields.Integer()
    loose_fruit_kg = fields.Float(digits=(16, 1))
    loose_left_kg = fields.Float(
        string="Loose Fruit Left (kg)", digits=(16, 1),
        help="Loose fruit left on the ground, found at inspection. Used for pay penalties.")
    est_weight_kg = fields.Float(compute='_compute_est_weight_kg', store=True, digits=(16, 1))

    _counts_positive = models.Constraint(
        'CHECK(bunches_ripe >= 0 AND bunches_unripe >= 0 AND bunches_overripe >= 0 '
        'AND loose_fruit_kg >= 0 AND loose_left_kg >= 0)',
        "Bunch counts and loose fruit weight cannot be negative.")

    @api.depends('bunches_ripe', 'bunches_overripe', 'loose_fruit_kg', 'block_id.avg_bunch_weight_kg')
    def _compute_est_weight_kg(self):
        for line in self:
            line.est_weight_kg = (
                (line.bunches_ripe + line.bunches_overripe) * line.block_id.avg_bunch_weight_kg
                + line.loose_fruit_kg)

    @api.constrains('block_id', 'tally_id')
    def _check_block(self):
        manager = self.env.user.has_group('ss_plantation.group_plantation_manager')
        for line in self:
            if line.block_id.division_id != line.tally_id.division_id:
                raise ValidationError(self.env._(
                    "Block %(block)s is not in division %(division)s.",
                    block=line.block_id.display_name, division=line.tally_id.division_id.display_name))
            if line.block_id.stage != 'mature' and not manager:
                raise ValidationError(self.env._(
                    "Block %(block)s is %(stage)s. Only mature blocks can be harvested.",
                    block=line.block_id.display_name, stage=line.block_id.stage))

    @api.constrains('block_id', 'harvester_id', 'tally_date')
    def _check_duplicates(self):
        for line in self:
            if self.search_count([
                ('id', '!=', line.id),
                ('block_id', '=', line.block_id.id),
                ('harvester_id', '=', line.harvester_id.id),
                ('tally_date', '=', line.tally_date),
                ('tally_state', '!=', 'cancel'),
            ], limit=1):
                raise ValidationError(self.env._(
                    "%(harvester)s already has a tally line for block %(block)s on %(date)s.",
                    harvester=line.harvester_id.name, block=line.block_id.display_name,
                    date=line.tally_date))
