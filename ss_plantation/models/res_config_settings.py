from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ss_ffb_product_id = fields.Many2one(related='company_id.ss_ffb_product_id', readonly=False)
    ss_cpo_product_id = fields.Many2one(related='company_id.ss_cpo_product_id', readonly=False)
    ss_kernel_product_id = fields.Many2one(related='company_id.ss_kernel_product_id', readonly=False)
    ss_warehouse_id = fields.Many2one(related='company_id.ss_warehouse_id', readonly=False)
    ss_consumption_location_id = fields.Many2one(
        related='company_id.ss_consumption_location_id', readonly=False)
    ss_estate_location_id = fields.Many2one(
        related='company_id.ss_estate_location_id', readonly=False)
    ss_freshness_hours = fields.Integer(related='company_id.ss_freshness_hours', readonly=False)
    group_ss_feature_payroll = fields.Boolean(
        string="Harvest Pay", implied_group='ss_plantation.group_ss_feature_payroll')
    group_ss_feature_asset = fields.Boolean(
        string="Mature Plantation Assets", implied_group='ss_plantation.group_ss_feature_asset')
    group_ss_feature_mill = fields.Boolean(
        string="Own Mill", implied_group='ss_plantation.group_ss_feature_mill')
