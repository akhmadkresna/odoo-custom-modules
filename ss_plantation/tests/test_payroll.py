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

    # ---- tiers and Sunday / holiday premium ----

    def _tally_kg(self, kg, date):
        """A tally giving the harvester exactly `kg` on `date` (the block weighs 20 kg a bunch)."""
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id,
            'bunches_ripe': int(kg / 20)}], date=date)

    def test_premium_tiers(self):
        # basis 800, first band 100/kg; beyond 300 kg above the basis the rate is 150/kg
        self.mixed.tier_ids = [(0, 0, {'above_kg': 300.0, 'rate_per_kg': 150.0})]
        self._tally_kg(1400, self.today)  # 600 kg above the basis
        pay = self._generate()
        self.assertAlmostEqual(pay.bonus_amount, 300 * 100.0 + 300 * 150.0)

    def test_tiers_do_not_change_pay_below_first_tier(self):
        self.mixed.tier_ids = [(0, 0, {'above_kg': 300.0, 'rate_per_kg': 150.0})]
        self._tally_kg(1000, self.today)  # 200 kg above the basis
        self.assertAlmostEqual(self._generate().bonus_amount, 20000.0)

    def test_tier_must_start_above_zero_and_be_unique(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.mixed.tier_ids = [(0, 0, {'above_kg': 0.0, 'rate_per_kg': 150.0})]
        self.mixed.tier_ids = [(0, 0, {'above_kg': 300.0, 'rate_per_kg': 150.0})]
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.mixed.tier_ids = [(0, 0, {'above_kg': 300.0, 'rate_per_kg': 160.0})]

    def test_sunday_premium(self):
        self.mixed.holiday_factor = 2.0
        sunday = fields.Date.to_date('2026-11-08')
        monday = fields.Date.to_date('2026-11-09')
        self._tally_kg(1000, sunday)  # 200 kg above the basis: 20,000, doubled on a Sunday
        self._tally_kg(1000, monday)  # an ordinary day: 20,000
        pay = self.env['ss.plantation.harvest.pay']._generate(sunday, monday, self.harvester)
        self.assertAlmostEqual(pay.bonus_amount, 40000.0 + 20000.0)

    def test_public_holiday_premium(self):
        self.mixed.holiday_factor = 1.5
        day = fields.Date.to_date('2026-11-10')  # a Tuesday
        self.env['resource.calendar.leaves'].sudo().create({
            'name': 'Test holiday', 'company_id': self.company.id,
            'date_from': '2026-11-09 17:00:00', 'date_to': '2026-11-10 16:59:59'})  # all of 10 Nov, Jakarta time
        self.harvester.tz = 'Asia/Jakarta'
        self._tally_kg(1000, day)
        pay = self.env['ss.plantation.harvest.pay']._generate(day, day, self.harvester)
        self.assertAlmostEqual(pay.bonus_amount, 20000.0 * 1.5)

    def test_piece_rate_sunday_premium(self):
        self.harvester.ss_pay_scheme_id = self.env['ss.plantation.pay.scheme'].create({
            'name': 'Piece Sunday', 'mode': 'piece_rate', 'rate_per_kg': 50.0, 'holiday_factor': 2.0})
        sunday = fields.Date.to_date('2026-11-08')
        self._tally_kg(1000, sunday)
        pay = self.env['ss.plantation.harvest.pay']._generate(sunday, sunday, self.harvester)
        self.assertAlmostEqual(pay.bonus_amount, 1000 * 50.0 * 2)

    def test_holiday_factor_below_one_refused(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.mixed.holiday_factor = 0.5
