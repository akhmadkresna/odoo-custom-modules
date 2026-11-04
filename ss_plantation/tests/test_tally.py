from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestTally(SsPlantationCommon):

    def test_est_weight(self):
        tally = self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id,
            'bunches_ripe': 100, 'bunches_overripe': 10, 'bunches_unripe': 7,
            'loose_fruit_kg': 25.0,
        }])
        line = tally.line_ids
        self.assertEqual(line.est_weight_kg, 110 * 20.0 + 25.0)
        self.assertEqual(tally.bunch_total, 110)
        self.assertEqual(self.block.last_harvest_date, tally.date)

    def test_duplicate_harvester_refused(self):
        vals = {'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 5}
        self._make_tally([vals])
        with self.assertRaises(ValidationError):
            self._make_tally([vals])

    def test_immature_block_refused_for_clerk(self):
        immature = self._make_block('TB02', 18.0, stage='immature')
        clerk = self.env['res.users'].sudo().create({
            'name': 'Clerk', 'login': 'clerk_ss',
            'group_ids': [Command.set([self.env.ref('ss_plantation.group_plantation_user').id])],
        })
        with self.assertRaises(ValidationError):
            self.env['ss.plantation.harvest.tally'].with_user(clerk).create({
                'division_id': self.division.id,
                'line_ids': [Command.create({
                    'block_id': immature.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 1})],
            })

    def test_block_must_belong_to_division(self):
        other = self.env['ss.plantation.division'].create({
            'name': 'Afdeling II', 'estate_id': self.estate.id})
        with self.assertRaises(ValidationError):
            self.env['ss.plantation.harvest.tally'].create({
                'division_id': other.id,
                'line_ids': [Command.create({
                    'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 1})],
            })
