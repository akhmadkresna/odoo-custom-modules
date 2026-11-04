from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestWeigh(SsPlantationCommon):

    def _ticket(self, **vals):
        return self.env['ss.plantation.weigh.ticket'].create({
            'gross_kg': 12000.0, 'tare_kg': 7500.0, 'plate': 'BM 1234 XX', **vals})

    def _percent(self, ticket, percent):
        ticket.grade_line_ids = [Command.create({
            'grade_type_id': self.env.ref('ss_plantation.grade_unripe').id, 'percent': percent})]

    def test_net_and_payable(self):
        ticket = self._ticket(direction='estate_in')
        self._percent(ticket, 3.0)
        self.assertEqual(ticket.net_kg, 4500.0)
        self.assertAlmostEqual(ticket.deduction_kg, 135.0)
        self.assertAlmostEqual(ticket.payable_kg, 4365.0)

    def test_tare_above_gross_refused(self):
        with self.assertRaises(ValidationError):
            self._ticket(gross_kg=1000.0, tare_kg=2000.0)

    def test_estate_receipt_creates_lot_and_stock(self):
        ticket = self._ticket(direction='estate_in')
        self._percent(ticket, 3.0)
        ticket.action_confirm()
        self.assertEqual(ticket.state, 'confirmed')
        self.assertEqual(ticket.lot_id.name, ticket.name)
        self.assertEqual(ticket.picking_id.state, 'done')
        stock = self.env['stock.quant']._get_available_quantity(
            self.ffb, self.warehouse.lot_stock_id, lot_id=ticket.lot_id)
        self.assertAlmostEqual(stock, 4365.0)

    def test_third_party_price_and_purchase(self):
        self.env['ss.plantation.ffb.price'].create({
            'date_from': fields.Date.today(), 'price_per_kg': 2800.0})
        ticket = self._ticket(direction='third_party_in', partner_id=self.supplier.id)
        self._percent(ticket, 3.0)
        self.assertEqual(ticket.unit_price, 2800.0)
        self.assertAlmostEqual(ticket.amount_total, 12222000.0, places=0)
        ticket.action_confirm()
        self.assertEqual(ticket.purchase_id.state, 'purchase')
        self.assertEqual(ticket.picking_id.state, 'done')
        self.assertEqual(ticket.purchase_id.order_line.price_unit, 2800.0)

    def test_sale_delivers_chosen_lot(self):
        receipt = self._ticket(direction='estate_in')
        receipt.action_confirm()
        sale = self._ticket(
            direction='out', partner_id=self.supplier.id, gross_kg=9000.0, tare_kg=7500.0,
            source_lot_id=receipt.lot_id.id)
        sale.action_confirm()
        self.assertEqual(sale.picking_id.state, 'done')
        left = self.env['stock.quant']._get_available_quantity(
            self.ffb, self.warehouse.lot_stock_id, lot_id=receipt.lot_id)
        self.assertAlmostEqual(left, 3000.0)

    def test_confirm_needs_partner_and_lot(self):
        with self.assertRaises(UserError):
            self._ticket(direction='third_party_in').action_confirm()
        with self.assertRaises(UserError):
            self._ticket(direction='out', partner_id=self.supplier.id).action_confirm()

    def test_stale_flag(self):
        note = self.env['ss.plantation.transport'].create({
            'division_id': self.division.id,
            'harvested_at': '2026-01-01 00:00:00',
            'line_ids': [Command.create({'block_id': self.block.id, 'bunches': 10})],
        })
        ticket = self._ticket(
            direction='estate_in', weigh_in_at='2026-01-01 10:00:00',
            transport_ids=[Command.link(note.id)])
        self.assertEqual(ticket.delay_hours, 10.0)
        self.assertTrue(ticket.too_stale)
        ticket.weigh_in_at = '2026-01-01 06:00:00'
        self.assertFalse(ticket.too_stale)
