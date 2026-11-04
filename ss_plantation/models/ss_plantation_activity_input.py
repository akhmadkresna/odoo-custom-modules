from odoo import api, fields, models
from odoo.exceptions import UserError


class SsPlantationActivityInput(models.Model):
    _name = 'ss.plantation.activity.input'
    _description = 'Plantation Activity Input'
    _check_company_auto = True

    activity_id = fields.Many2one(
        'ss.plantation.activity', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='activity_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', required=True, check_company=True, domain="[('is_storable', '=', True)]")
    qty = fields.Float(string="Quantity", required=True, digits='Product Unit')
    uom_id = fields.Many2one(
        'uom.uom', string="Unit", compute='_compute_uom_id', store=True, readonly=False,
        precompute=True, required=True)
    move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    reverse_move_id = fields.Many2one('stock.move', readonly=True, copy=False)

    _qty_positive = models.Constraint('CHECK(qty > 0)', "The input quantity must be positive.")

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    def _move_vals(self, source, dest):
        self.ensure_one()
        activity = self.activity_id
        return {
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty,
            'uom_id': self.uom_id.id,
            'quantity': self.qty,
            'picked': True,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'company_id': activity.company_id.id,
            'origin': activity.name,
            'ss_plantation_block_id': activity.block_id.id,
        }

    def _consume(self):
        for line in self:
            company = line.activity_id.company_id
            source = line.activity_id.division_id.store_location_id
            dest = company.ss_consumption_location_id
            if not source or not dest:
                raise UserError(self.env._(
                    "Set the input store on division %(division)s and the consumption location "
                    "in the Plantation settings.", division=line.activity_id.division_id.display_name))
            move = self.env['stock.move'].create(line._move_vals(source, dest))
            move._action_confirm()
            move._action_done()
            line.move_id = move

    def _reverse(self):
        for line in self.filtered(lambda l: l.move_id and not l.reverse_move_id):
            move = line.move_id
            back = self.env['stock.move'].create(
                line._move_vals(move.location_dest_id, move.location_id))
            back._action_confirm()
            back._action_done()
            line.reverse_move_id = back
