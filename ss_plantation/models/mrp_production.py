from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    ss_ffb_kg = fields.Float(
        string="FFB Processed (kg)", compute='_compute_ss_extraction', store=True, digits=(16, 1))
    ss_cpo_kg = fields.Float(
        string="CPO Produced (kg)", compute='_compute_ss_extraction', store=True, digits=(16, 1))
    ss_kernel_kg = fields.Float(
        string="Kernel Produced (kg)", compute='_compute_ss_extraction', store=True, digits=(16, 1))
    ss_oer = fields.Float(
        string="OER (%)", compute='_compute_ss_extraction', store=True, digits=(16, 2),
        aggregator='avg', help="Oil extraction rate: CPO divided by FFB processed.")
    ss_ker = fields.Float(
        string="KER (%)", compute='_compute_ss_extraction', store=True, digits=(16, 2),
        aggregator='avg', help="Kernel extraction rate: kernel divided by FFB processed.")

    @api.depends(
        'state', 'company_id.ss_ffb_product_id', 'company_id.ss_cpo_product_id',
        'company_id.ss_kernel_product_id', 'move_raw_ids.quantity', 'move_raw_ids.product_id',
        'move_finished_ids.quantity', 'move_finished_ids.product_id')
    def _compute_ss_extraction(self):
        for mo in self:
            company = mo.company_id
            ffb = sum(mo.move_raw_ids.filtered(
                lambda m: m.product_id == company.ss_ffb_product_id).mapped('quantity'))
            cpo = sum(mo.move_finished_ids.filtered(
                lambda m: m.product_id == company.ss_cpo_product_id).mapped('quantity'))
            kernel = sum(mo.move_finished_ids.filtered(
                lambda m: m.product_id == company.ss_kernel_product_id).mapped('quantity'))
            mo.ss_ffb_kg, mo.ss_cpo_kg, mo.ss_kernel_kg = ffb, cpo, kernel
            mo.ss_oer = 100.0 * cpo / ffb if ffb else 0.0
            mo.ss_ker = 100.0 * kernel / ffb if ffb else 0.0
