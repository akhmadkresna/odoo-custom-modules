from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestPlantationUom(SsPlantationCommon):
    """Weights stay in kg whatever unit the FFB, CPO and kernel products are stocked in."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.production_location = cls.env['stock.location'].search(
            [('usage', '=', 'production')], limit=1)
        cls.kg = cls.env.ref('uom.product_uom_kgm')
        cls.tonne = cls.env.ref('uom.product_uom_ton')
        cls.ffb_t = cls._product('Test FFB (tonne)', cls.tonne, tracking='lot')
        cls.cpo_t = cls._product('Test CPO (tonne)', cls.tonne)
        cls.kernel_kg = cls._product('Test Kernel (kg)', cls.kg)
        cls.company.write({
            'ss_ffb_product_id': cls.ffb_t.id, 'ss_cpo_product_id': cls.cpo_t.id,
            'ss_kernel_product_id': cls.kernel_kg.id})

    @classmethod
    def _product(cls, name, uom, tracking=False):
        return cls.env['product.product'].create({
            'name': name, 'type': 'consu', 'is_storable': True, 'uom_id': uom.id,
            'tracking': tracking})

    def test_ticket_stock_follows_product_unit(self):
        """4,875 kg payable is received as 4.875 tonnes, not 4,875 tonnes."""
        ticket = self.env['ss.plantation.weigh.ticket'].create({
            'direction': 'estate_in', 'gross_kg': 5000, 'tare_kg': 0,
            'grade_line_ids': [(0, 0, {
                'grade_type_id': self.env.ref('ss_plantation.grade_dirt').id, 'kg': 125})],
        })
        ticket.action_confirm()
        self.assertEqual(ticket.state, 'confirmed')
        self.assertEqual(ticket.payable_kg, 4875)
        self.assertEqual(ticket.picking_id.state, 'done')
        move = ticket.picking_id.move_ids
        self.assertEqual(move.uom_id, self.tonne)
        # stock in tonnes is kept to the unit's precision (0.01 t)
        self.assertAlmostEqual(move.quantity, 4.875, delta=0.005)
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.ffb_t.id), ('lot_id', '=', ticket.lot_id.id),
            ('location_id', '=', self.warehouse.lot_stock_id.id)])
        self.assertAlmostEqual(quant.quantity, 4.875, delta=0.005)

    def test_purchase_price_is_per_product_unit(self):
        """Rp 2,000/kg becomes Rp 2,000,000 per tonne on the purchase line."""
        ticket = self.env['ss.plantation.weigh.ticket'].create({
            'direction': 'third_party_in', 'partner_id': self.supplier.id,
            'gross_kg': 3000, 'tare_kg': 0, 'unit_price': 2000.0,
        })
        ticket.action_confirm()
        line = ticket.purchase_id.order_line
        self.assertAlmostEqual(line.product_qty, 3.0, places=3)
        self.assertAlmostEqual(line.price_unit, 2000000.0, places=2)
        self.assertAlmostEqual(line.price_subtotal, 6000000.0, places=2)
        self.assertAlmostEqual(ticket.amount_total, 6000000.0, places=2)

    def test_extraction_rates_in_kg_for_tonne_products(self):
        """OER and KER are right when FFB and CPO are moved in tonnes."""
        mo = self.env['mrp.production'].create({
            'product_id': self.cpo_t.id, 'product_qty': 1.0, 'uom_id': self.tonne.id,
            'move_raw_ids': [(0, 0, {
                'product_id': self.ffb_t.id, 'product_uom_qty': 5.0, 'uom_id': self.tonne.id,
                'location_id': self.warehouse.lot_stock_id.id,
                'location_dest_id': self.production_location.id})],
        })
        mo.move_raw_ids.quantity = 5.0
        mo.move_finished_ids.filtered(lambda m: m.product_id == self.cpo_t).quantity = 1.0
        self.env['stock.move'].create({
            'product_id': self.kernel_kg.id, 'product_uom_qty': 250.0, 'uom_id': self.kg.id,
            'quantity': 250.0, 'production_id': mo.id,
            'location_id': self.production_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        self.assertEqual(mo.ss_ffb_kg, 5000.0)
        self.assertEqual(mo.ss_cpo_kg, 1000.0)
        self.assertEqual(mo.ss_kernel_kg, 250.0)
        self.assertAlmostEqual(mo.ss_oer, 20.0)
        self.assertAlmostEqual(mo.ss_ker, 5.0)
