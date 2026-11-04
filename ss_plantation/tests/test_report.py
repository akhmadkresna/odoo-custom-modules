from odoo import Command
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestYieldReport(SsPlantationCommon):

    def test_yield_allocation(self):
        note = self.env['ss.plantation.transport'].create({
            'division_id': self.division.id,
            'line_ids': [
                Command.create({'block_id': self.block.id, 'bunches': 100}),
                Command.create({'block_id': self.block_b.id, 'bunches': 300}),
            ],
        })
        ticket = self.env['ss.plantation.weigh.ticket'].create({
            'direction': 'estate_in', 'gross_kg': 9000.0, 'tare_kg': 5000.0,
            'transport_ids': [Command.link(note.id)],
        })
        ticket.action_confirm()
        self._make_tally([{
            'block_id': self.block.id, 'harvester_id': self.harvester.id, 'bunches_ripe': 100}])
        self.env.flush_all()
        rows = self.env['ss.plantation.yield.report'].search(
            [('block_id', 'in', (self.block + self.block_b).ids)])
        weighed = {}
        for row in rows:
            weighed[row.block_id] = weighed.get(row.block_id, 0.0) + row.weighed_kg
        self.assertAlmostEqual(weighed[self.block], 1000.0)
        self.assertAlmostEqual(weighed[self.block_b], 3000.0)
        estimated = sum(rows.filtered(lambda r: r.block_id == self.block).mapped('est_weight_kg'))
        self.assertAlmostEqual(estimated, 2000.0)
