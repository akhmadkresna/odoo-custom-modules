from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestBlockAsset(SsPlantationCommon):

    def _wizard(self, block):
        Account = self.env['account.account']
        model = self.env['account.depreciation.model'].create({
            'name': 'Plantation 25 years', 'method': 'linear', 'method_number': 25.0,
            'method_period': '12', 'prorata_computation_type': 'constant_periods'})
        asset_account = Account.create({
            'name': 'Mature plantation', 'code': 'SS150', 'account_type': 'asset_fixed',
            'depreciation_model_id': model.id})
        counterpart = Account.create({
            'name': 'Plantation development cost', 'code': 'SS151', 'account_type': 'asset_current'})
        journal = self.env['account.journal'].create({
            'name': 'Plantation misc', 'code': 'SSPM', 'type': 'general'})
        return self.env['ss.plantation.block.asset.wizard'].create({
            'block_id': block.id, 'name': 'Block asset', 'original_value': 1000000.0,
            'account_asset_id': asset_account.id, 'counterpart_account_id': counterpart.id,
            'journal_id': journal.id,
        })

    def test_mature_wizard_creates_asset(self):
        wizard = self._wizard(self.block)
        wizard.action_create_asset()
        asset = self.block.asset_id
        self.assertTrue(asset)
        self.assertEqual(asset.original_value, 1000000.0)
        self.assertEqual(asset.state, 'draft')

    def test_immature_block_cannot_be_capitalised(self):
        block = self._make_block('TC01', 18.0, stage='immature')
        with self.assertRaises(UserError):
            self._wizard(block).action_create_asset()

    def test_block_capitalised_once(self):
        self._wizard(self.block).action_create_asset()
        with self.assertRaises(UserError):
            self._wizard(self.block).action_create_asset()

    def test_account_without_depreciation_model_is_refused(self):
        wizard = self._wizard(self.block)
        wizard.account_asset_id.depreciation_model_id = False
        with self.assertRaisesRegex(UserError, "depreciation model"):
            wizard.action_create_asset()
        self.assertFalse(self.block.asset_id)
