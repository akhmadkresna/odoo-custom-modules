from odoo import api, fields, models
from odoo.exceptions import UserError


class SsPlantationActivity(models.Model):
    _name = 'ss.plantation.activity'
    _description = 'Plantation Field Activity'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/')
    date = fields.Date(required=True, default=fields.Date.context_today)
    block_id = fields.Many2one(
        'ss.plantation.block', required=True, index=True, check_company=True, ondelete='restrict')
    division_id = fields.Many2one(related='block_id.division_id', store=True, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    type_id = fields.Many2one('ss.plantation.activity.type', required=True)
    uom_basis = fields.Selection(related='type_id.uom_basis')
    quantity = fields.Float(string="Quantity (ha / palms)")
    man_days = fields.Float()
    employee_ids = fields.Many2many('hr.employee', string="Workers", check_company=True)
    input_line_ids = fields.One2many('ss.plantation.activity.input', 'activity_id', copy=True)
    state = fields.Selection(
        [('draft', "Draft"), ('done', "Done"), ('cancel', "Cancelled")],
        default='draft', required=True, index=True, copy=False)
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('ss.plantation.activity') or '/'
        return super().create(vals_list)

    @api.onchange('type_id', 'block_id')
    def _onchange_type_id(self):
        if self.type_id.uom_basis == 'ha' and self.block_id and not self.quantity:
            self.quantity = self.block_id.area_ha

    def write(self, vals):
        if set(vals) - {'note', 'state'} and any(a.state != 'draft' for a in self):
            raise UserError(self.env._("Only draft activities can be edited."))
        return super().write(vals)

    def action_done(self):
        for activity in self.filtered(lambda a: a.state == 'draft'):
            activity.input_line_ids._consume()
            activity.state = 'done'

    def action_cancel(self):
        for activity in self:
            if activity.state == 'done':
                activity.input_line_ids._reverse()
            activity.state = 'cancel'

    def action_draft(self):
        self.filtered(lambda a: a.state == 'cancel').state = 'draft'
