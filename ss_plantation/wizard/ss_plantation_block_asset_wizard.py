from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class SsPlantationBlockAssetWizard(models.TransientModel):
    _name = 'ss.plantation.block.asset.wizard'
    _description = 'Capitalise Mature Block'

    block_id = fields.Many2one('ss.plantation.block', required=True, readonly=True)
    company_id = fields.Many2one(related='block_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    name = fields.Char(required=True)
    acquisition_date = fields.Date(required=True, default=fields.Date.context_today)
    original_value = fields.Monetary(required=True, currency_field='currency_id')
    account_asset_id = fields.Many2one(
        'account.account', string="Asset Account", required=True, check_company=True,
        domain="[('account_type', '=', 'asset_fixed')]")
    counterpart_account_id = fields.Many2one(
        'account.account', string="Counterpart Account", required=True, check_company=True,
        help="Account holding the development cost until it is capitalised.")
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', '=', 'general')]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        block = self.env['ss.plantation.block'].browse(
            self.env.context.get('default_block_id') or res.get('block_id'))
        if block:
            res.setdefault('name', self.env._("Plantation %s", block.display_name))
            res.setdefault('original_value', block.cost_total)
            res.setdefault('acquisition_date', block.mature_date or fields.Date.context_today(self))
        return res

    def action_create_asset(self):
        self.ensure_one()
        block = self.block_id
        if block.stage != 'mature':
            raise UserError(self.env._("Only a mature block can be capitalised."))
        if block.asset_id:
            raise UserError(self.env._("Block %s already has an asset.", block.display_name))
        if not self.account_asset_id.depreciation_model_id:
            raise UserError(self.env._(
                "Account %s has no depreciation model. Set one on the account "
                "(Accounting > Configuration > Chart of Accounts) before capitalising a block.",
                self.account_asset_id.display_name))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.acquisition_date,
            'ref': self.env._("Capitalisation of %s", block.display_name),
            'line_ids': [
                Command.create({
                    'account_id': self.account_asset_id.id,
                    'name': self.name,
                    'debit': self.original_value,
                    'analytic_distribution': {str(block.analytic_account_id.id): 100.0},
                }),
                Command.create({
                    'account_id': self.counterpart_account_id.id,
                    'name': self.name,
                    'credit': self.original_value,
                }),
            ],
        })
        asset = self.env['account.asset'].create({
            'name': self.name,
            'company_id': self.company_id.id,
            'account_asset_id': self.account_asset_id.id,
            'original_value': self.original_value,
            'acquisition_date': self.acquisition_date,
            'original_move_line_ids': [Command.set(move.line_ids.filtered('debit').ids)],
        })
        block.asset_id = asset
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset',
            'res_id': asset.id,
            'view_mode': 'form',
        }
