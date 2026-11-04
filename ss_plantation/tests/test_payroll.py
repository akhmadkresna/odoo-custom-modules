from odoo import fields
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestHarvestPay(SsPlantationCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mixed = cls.env['ss.plantation.pay.scheme'].create({
            'name': 'Basis plus bonus', 'mode': 'mixed', 'basis_kg': 800.0,
            'bonus_per_kg': 100.0, 'penalty_unripe': 500.0, 'penalty_loose_left': 200.0})
        cls.harvester.ss_pay_scheme_id = cls.mixed
        cls.today = fields.Date.today()

    def _generate(self):
        return self.env['ss.plantation.harvest.pay']._generate(
            self.today, self.today, self.harvester)

    def test_bonus_over_basis(self):
        # 50 bunches x 20 kg = 1,000 kg, 200 kg above the 800 kg basis
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 50}])
        pay = self._generate()
        self.assertAlmostEqual(pay.harvested_kg, 1000.0)
        self.assertAlmostEqual(pay.bonus_amount, 20000.0)
        self.assertAlmostEqual(pay.amount, 20000.0)

    def test_penalties_reduce_pay(self):
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 50,
            'bunches_unripe': 10, 'loose_left_kg': 25.0}])
        pay = self._generate()
        self.assertAlmostEqual(pay.penalty_amount, 10 * 500.0 + 25 * 200.0)
        self.assertAlmostEqual(pay.amount, 20000.0 - 10000.0)

    def test_below_basis_pays_nothing_extra(self):
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 30}])
        self.assertEqual(self._generate().amount, 0.0)

    def test_piece_rate(self):
        self.harvester.ss_pay_scheme_id = self.env['ss.plantation.pay.scheme'].create({
            'name': 'Piece', 'mode': 'piece_rate', 'rate_per_kg': 50.0})
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 50}])
        self.assertAlmostEqual(self._generate().amount, 50000.0)

    def test_regenerate_replaces_draft(self):
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 50}])
        self._generate()
        self._generate()
        self.assertEqual(self.env['ss.plantation.harvest.pay'].search_count(
            [('employee_id', '=', self.harvester.id)]), 1)
