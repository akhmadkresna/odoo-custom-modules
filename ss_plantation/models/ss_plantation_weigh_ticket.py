from odoo import Command, api, fields, models
from odoo.fields import Domain
from odoo.exceptions import UserError, ValidationError


class SsPlantationWeighTicket(models.Model):
    _name = 'ss.plantation.weigh.ticket'
    _description = 'Plantation Weigh Ticket'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(readonly=True, copy=False, default='/')
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    direction = fields.Selection(
        [('estate_in', "Own Estate to Mill"), ('third_party_in', "Bought from Third Party"),
         ('out', "Sold")],
        required=True, default='estate_in', index=True)
    partner_id = fields.Many2one('res.partner', string="Partner", check_company=True, index=True)
    plate = fields.Char()
    driver_name = fields.Char()
    weigh_in_at = fields.Datetime(string="Weighed In")
    weigh_out_at = fields.Datetime(string="Weighed Out")
    gross_kg = fields.Float(digits=(16, 1))
    tare_kg = fields.Float(digits=(16, 1))
    net_kg = fields.Float(compute='_compute_weights', store=True, digits=(16, 1))
    deduction_kg = fields.Float(compute='_compute_weights', store=True, digits=(16, 1))
    payable_kg = fields.Float(compute='_compute_weights', store=True, digits=(16, 1))
    grade_line_ids = fields.One2many('ss.plantation.weigh.grade.line', 'ticket_id', copy=True)
    unit_price = fields.Monetary(
        string="Price / kg", compute='_compute_unit_price', store=True, readonly=False,
        currency_field='currency_id')
    amount_total = fields.Monetary(
        compute='_compute_amount_total', store=True, currency_field='currency_id')
    transport_ids = fields.One2many('ss.plantation.transport', 'ticket_id', string="Transport Notes")
    delay_hours = fields.Float(
        string="Harvest to Weigh-in (h)", compute='_compute_delay_hours', store=True,
        digits=(16, 1))
    too_stale = fields.Boolean(compute='_compute_delay_hours', store=True)
    source_lot_id = fields.Many2one(
        'stock.lot', string="Lot Sold", check_company=True,
        help="Lot delivered. Required for sales.")
    lot_id = fields.Many2one('stock.lot', readonly=True, copy=False, check_company=True)
    picking_id = fields.Many2one('stock.picking', readonly=True, copy=False)
    purchase_id = fields.Many2one('purchase.order', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', "Draft"), ('confirmed', "Confirmed"), ('cancel', "Cancelled")],
        default='draft', required=True, index=True, copy=False)
    note = fields.Text()

    @api.depends('gross_kg', 'tare_kg', 'grade_line_ids.deduction_kg')
    def _compute_weights(self):
        for ticket in self:
            ticket.net_kg = ticket.gross_kg - ticket.tare_kg
            ticket.deduction_kg = sum(ticket.grade_line_ids.mapped('deduction_kg'))
            ticket.payable_kg = ticket.net_kg - ticket.deduction_kg

    @api.depends('direction', 'date', 'partner_id', 'company_id')
    def _compute_unit_price(self):
        price_model = self.env['ss.plantation.ffb.price']
        for ticket in self:
            if ticket.direction == 'third_party_in':
                ticket.unit_price = price_model._get_price(
                    ticket.company_id, ticket.date, ticket.partner_id)
            else:
                ticket.unit_price = ticket.unit_price or 0.0

    @api.depends('payable_kg', 'unit_price')
    def _compute_amount_total(self):
        for ticket in self:
            ticket.amount_total = ticket.currency_id.round(ticket.payable_kg * ticket.unit_price)

    @api.depends('weigh_in_at', 'transport_ids.harvested_at', 'company_id.ss_freshness_hours')
    def _compute_delay_hours(self):
        for ticket in self:
            harvested = [h for h in ticket.transport_ids.mapped('harvested_at') if h]
            if ticket.weigh_in_at and harvested:
                delta = ticket.weigh_in_at - min(harvested)
                ticket.delay_hours = delta.total_seconds() / 3600.0
            else:
                ticket.delay_hours = 0.0
            limit = ticket.company_id.ss_freshness_hours
            ticket.too_stale = bool(limit) and ticket.delay_hours > limit

    @api.constrains('gross_kg', 'tare_kg', 'grade_line_ids')
    def _check_weights(self):
        for ticket in self:
            if ticket.gross_kg < 0 or ticket.tare_kg < 0:
                raise ValidationError(self.env._("Weights cannot be negative."))
            if ticket.net_kg < 0:
                raise ValidationError(self.env._("Tare weight cannot exceed gross weight."))
            if ticket.payable_kg < 0:
                raise ValidationError(self.env._("Grade deductions exceed the net weight."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('ss.plantation.weigh.ticket') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {'state', 'note'} and any(t.state == 'confirmed' for t in self):
            if not self.env.user.has_group('ss_plantation.group_plantation_manager'):
                raise UserError(self.env._("A confirmed weigh ticket can only be changed by a manager."))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------
    def _kg_to_product_qty(self, product, kg):
        """`kg` expressed in the stock unit of `product` (kg, tonne, ...)."""
        kgm = self.env.ref('uom.product_uom_kgm')
        return kgm._compute_quantity(kg, product.uom_id, round=False)

    def _check_ready(self):
        self.ensure_one()
        company = self.company_id
        if not company.ss_ffb_product_id or not company.ss_warehouse_id:
            raise UserError(self.env._(
                "Set the FFB product and receiving warehouse in the Plantation settings."))
        if self.direction != 'estate_in' and not self.partner_id:
            raise UserError(self.env._("Ticket %s needs a partner.", self.name))
        if self.direction == 'estate_in' and not company.ss_estate_location_id:
            raise UserError(self.env._("Set the estate harvest location in the Plantation settings."))
        if self.direction == 'out' and not self.source_lot_id:
            raise UserError(self.env._("Choose the lot sold on ticket %s.", self.name))
        if self.payable_kg <= 0:
            raise UserError(self.env._("Ticket %s has no payable weight.", self.name))
        try:
            self._kg_to_product_qty(company.ss_ffb_product_id, 1.0)
        except UserError:
            raise UserError(self.env._(
                "The FFB product %(product)s is counted in %(uom)s, which cannot be converted from "
                "kilograms. Give it a weight unit such as kg or tonne.",
                product=company.ss_ffb_product_id.display_name,
                uom=company.ss_ffb_product_id.uom_id.display_name)) from None

    def action_confirm(self):
        for ticket in self.filtered(lambda t: t.state == 'draft'):
            ticket._check_ready()
            if ticket.direction == 'third_party_in':
                ticket._confirm_purchase()
            elif ticket.direction == 'estate_in':
                ticket._confirm_estate_receipt()
            else:
                ticket._confirm_sale()
            ticket.transport_ids.filtered(lambda n: n.state != 'cancel').state = 'weighed'
            ticket.state = 'confirmed'

    def _new_lot(self):
        self.ensure_one()
        return self.env['stock.lot'].create({
            'name': self.name,
            'product_id': self.company_id.ss_ffb_product_id.id,
            'company_id': self.company_id.id,
        })

    def _set_lot_and_validate(self, picking, lot, qty):
        """Fill the picking's single move line with the lot and quantity, then validate it."""
        move = picking.move_ids
        if not move.move_line_ids:
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': move.product_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            })
        lines = move.move_line_ids
        lines[1:].unlink()
        lines[0].write({'lot_id': lot.id, 'quantity': qty})
        move.picked = True
        picking.with_context(
            skip_immediate=True, skip_backorder=True, skip_sms=True).button_validate()

    def _confirm_estate_receipt(self):
        self.ensure_one()
        company = self.company_id
        warehouse = company.ss_warehouse_id
        product = company.ss_ffb_product_id
        lot = self._new_lot()
        qty = self._kg_to_product_qty(product, self.payable_kg)
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': company.ss_estate_location_id.id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'origin': self.name,
            'company_id': company.id,
            'move_ids': [Command.create({
                'product_id': product.id,
                'product_uom_qty': qty,
                'uom_id': product.uom_id.id,
                'location_id': company.ss_estate_location_id.id,
                'location_dest_id': warehouse.lot_stock_id.id,
                'company_id': company.id,
            })],
        })
        picking.action_confirm()
        self._set_lot_and_validate(picking, lot, qty)
        self.write({'lot_id': lot.id, 'picking_id': picking.id})

    def _confirm_purchase(self):
        self.ensure_one()
        company = self.company_id
        warehouse = company.ss_warehouse_id
        product = company.ss_ffb_product_id
        qty = self._kg_to_product_qty(product, self.payable_kg)
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': company.id,
            'origin': self.name,
            'picking_type_id': warehouse.in_type_id.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_qty': qty,
                'uom_id': product.uom_id.id,
                'price_unit': self.unit_price / self._kg_to_product_qty(product, 1.0) if self.unit_price else 0.0,
            })],
        })
        order.button_confirm()
        picking = order.picking_ids[:1]
        lot = self._new_lot()
        self._set_lot_and_validate(picking, lot, qty)
        self.write({'lot_id': lot.id, 'picking_id': picking.id, 'purchase_id': order.id})

    def _confirm_sale(self):
        self.ensure_one()
        company = self.company_id
        warehouse = company.ss_warehouse_id
        product = company.ss_ffb_product_id
        customer_location = self.partner_id.property_stock_customer
        qty = self._kg_to_product_qty(product, self.payable_kg)
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': self.partner_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': customer_location.id,
            'origin': self.name,
            'company_id': company.id,
            'move_ids': [Command.create({
                'product_id': product.id,
                'product_uom_qty': qty,
                'uom_id': product.uom_id.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': customer_location.id,
                'company_id': company.id,
            })],
        })
        picking.action_confirm()
        self._set_lot_and_validate(picking, self.source_lot_id, qty)
        self.write({'lot_id': self.source_lot_id.id, 'picking_id': picking.id})

    def action_cancel(self):
        if any(t.state == 'confirmed' for t in self):
            raise UserError(self.env._(
                "A confirmed ticket cannot be cancelled. Return the stock and issue a new ticket."))
        self.state = 'cancel'

    def action_draft(self):
        self.filtered(lambda t: t.state == 'cancel').state = 'draft'

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'stock.picking',
            'res_id': self.picking_id.id, 'view_mode': 'form'}

    def action_view_tally_lines(self):
        """Traceability: tally lines of the blocks/date on this ticket's transport notes."""
        self.ensure_one()
        leaves = [
            Domain([('block_id', '=', block.id), ('tally_date', '=', note.date)])
            for note in self.transport_ids for block in note.line_ids.block_id]
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Tally lines"),
            'res_model': 'ss.plantation.harvest.tally.line',
            'view_mode': 'list',
            'domain': list(Domain.OR(leaves)) if leaves else [('id', '=', 0)],
        }
