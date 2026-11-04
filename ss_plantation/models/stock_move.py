from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    ss_plantation_block_id = fields.Many2one(
        'ss.plantation.block', string="Plantation Block", index='btree_not_null', copy=False)

    def _get_analytic_distribution(self):
        distribution = dict(super()._get_analytic_distribution())
        account = self.ss_plantation_block_id.analytic_account_id
        if account:
            distribution[str(account.id)] = 100.0
        return distribution
