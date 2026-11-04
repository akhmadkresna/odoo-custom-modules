from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.safe_eval import safe_eval

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestBlock(SsPlantationCommon):

    def test_block_creates_analytic(self):
        plan = self.env.ref('ss_plantation.analytic_plan_block')
        self.assertTrue(self.block.analytic_account_id)
        self.assertEqual(self.block.analytic_account_id.plan_id, plan)

    def test_block_delete_blocked_with_history(self):
        self.env['ss.plantation.activity'].create({
            'block_id': self.block.id,
            'type_id': self.env.ref('ss_plantation.activity_type_weeding').id,
        })
        with self.assertRaises(UserError):
            self.block.unlink()
        self.block_b.unlink()

    def test_set_mature_sets_date(self):
        block = self._make_block('TB01', 18.0, stage='immature')
        self.assertFalse(block.mature_date)
        block.action_set_mature()
        self.assertEqual(block.stage, 'mature')
        self.assertTrue(block.mature_date)

    @mute_logger('odoo.sql_db')
    def test_code_unique_and_area_positive(self):
        with self.assertRaises(Exception), self.cr.savepoint():
            self._make_block('TA01', 18.0)
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['ss.plantation.block'].create({
                'name': 'Zero', 'code': 'Z', 'division_id': self.division.id, 'area_ha': 0})

    def test_new_record_can_pick_division_and_estate(self):
        """A new block has no company yet, so its division choices must not depend on it."""
        ctx = {'allowed_company_ids': self.company.ids}
        for model, field, record in (
                ('ss.plantation.block', 'division_id', self.division),
                ('ss.plantation.division', 'estate_id', self.estate)):
            domain = self.env[model].fields_get([field])[field]['domain']
            domain = safe_eval(domain, ctx)
            self.assertIn(record, self.env[record._name].search(domain))

    def test_division_area(self):
        self.assertEqual(self.division.area_ha, 50.0)
