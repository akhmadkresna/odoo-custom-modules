from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ss_ffb_product_id = fields.Many2one(
        'product.product', string="FFB Product", domain="[('is_storable', '=', True)]")
    ss_cpo_product_id = fields.Many2one(
        'product.product', string="CPO Product", domain="[('is_storable', '=', True)]")
    ss_kernel_product_id = fields.Many2one(
        'product.product', string="Kernel Product", domain="[('is_storable', '=', True)]")
    ss_warehouse_id = fields.Many2one('stock.warehouse', string="Receiving Warehouse")
    ss_consumption_location_id = fields.Many2one(
        'stock.location', string="Plantation Consumption Location",
        domain="[('usage', '=', 'inventory')]")
    ss_estate_location_id = fields.Many2one(
        'stock.location', string="Estate Harvest Location", domain="[('usage', '=', 'production')]")
    ss_freshness_hours = fields.Integer(string="FFB Freshness Limit (hours)", default=8)
