from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestMill(SsPlantationCommon):

    def test_oer_and_ker(self):
        cpo = self.company.ss_cpo_product_id
        kernel = self.company.ss_kernel_product_id
        mo = self.env['mrp.production'].create({
            'product_id': cpo.id, 'product_qty': 2200.0,
            'bom_id': self.env['mrp.bom']._bom_find(cpo)[cpo].id,
        })
        mo.action_confirm()
        mo.move_raw_ids.filtered(lambda m: m.product_id == self.ffb).quantity = 10000.0
        mo.move_finished_ids.filtered(lambda m: m.product_id == cpo).quantity = 2200.0
        mo.move_finished_ids.filtered(lambda m: m.product_id == kernel).quantity = 500.0
        self.assertAlmostEqual(mo.ss_ffb_kg, 10000.0)
        self.assertAlmostEqual(mo.ss_oer, 22.0)
        self.assertAlmostEqual(mo.ss_ker, 5.0)
