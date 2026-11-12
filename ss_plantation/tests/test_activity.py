from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestActivity(SsPlantationCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fertiliser = cls.env['product.product'].create({
            'name': 'NPK', 'is_storable': True, 'standard_price': 10.0,
            'uom_id': cls.env.ref('uom.product_uom_kgm').id,
        })
        cls.env['stock.quant']._update_available_quantity(cls.fertiliser, cls.store, 50.0)

    def _activity(self, qty=20.0):
        return self.env['ss.plantation.activity'].create({
            'block_id': self.block.id,
            'type_id': self.env.ref('ss_plantation.activity_type_fertilising').id,
            'input_line_ids': [Command.create({'product_id': self.fertiliser.id, 'qty': qty})],
        })

    def test_input_consumes_stock_and_cost(self):
        activity = self._activity()
        activity.action_done()
        self.assertEqual(activity.state, 'done')
        free = self.env['stock.quant']._get_available_quantity(self.fertiliser, self.store)
        self.assertEqual(free, 30.0)
        self.assertAlmostEqual(self.block.cost_total, 200.0)
        self.assertAlmostEqual(self.block.cost_per_ha, 200.0 / 25.0)

    def test_cancel_reverses_stock_and_cost(self):
        activity = self._activity()
        activity.action_done()
        activity.action_cancel()
        free = self.env['stock.quant']._get_available_quantity(self.fertiliser, self.store)
        self.assertEqual(free, 50.0)
        self.assertAlmostEqual(self.block.cost_total, 0.0)

    def test_inputs_only_for_types_using_stock(self):
        weeding = self.env.ref('ss_plantation.activity_type_weeding')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env['ss.plantation.activity'].create({
                'block_id': self.block.id, 'type_id': weeding.id,
                'input_line_ids': [Command.create({'product_id': self.fertiliser.id, 'qty': 1.0})],
            })

    def test_done_requires_inputs_when_type_uses_stock(self):
        activity = self._activity()
        activity.input_line_ids.unlink()
        with self.assertRaises(UserError):
            activity.action_done()
