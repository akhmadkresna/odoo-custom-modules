from odoo import fields, models


class SsPlantationPayScheme(models.Model):
    _name = 'ss.plantation.pay.scheme'
    _description = 'Plantation Harvest Pay Scheme'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    mode = fields.Selection(
        [('daily', "Daily wage (penalties only)"),
         ('piece_rate', "Piece rate (per kg)"),
         ('mixed', "Daily basis plus bonus above it")],
        required=True, default='mixed',
        help="Daily wage itself stays in the normal payroll contract. This scheme only "
             "adds the harvest bonus, or the piece-rate pay, minus penalties.")
    rate_per_kg = fields.Monetary(
        string="Piece Rate / kg", currency_field='currency_id',
        help="Piece rate mode: paid on every harvested kg.")
    basis_kg = fields.Float(
        string="Daily Basis (kg)", digits=(16, 1),
        help="Mixed mode: kilograms a harvester must reach per day before the bonus starts.")
    bonus_per_kg = fields.Monetary(
        string="Bonus / kg above Basis", currency_field='currency_id')
    penalty_unripe = fields.Monetary(
        string="Penalty / Unripe Bunch", currency_field='currency_id')
    penalty_loose_left = fields.Monetary(
        string="Penalty / kg Loose Fruit Left", currency_field='currency_id')
