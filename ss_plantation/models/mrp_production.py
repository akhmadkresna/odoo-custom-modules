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
        'move_raw_ids.uom_id', 'move_finished_ids.quantity', 'move_finished_ids.product_id',
        'move_finished_ids.uom_id')
    def _compute_ss_extraction(self):
        kg = self.env.ref('uom.product_uom_kgm')

        def kg_of(moves):
            # a move may be in any weight unit (kg, tonne, ...): always report kilograms
            return sum(
                move.uom_id._compute_quantity(
                    move.quantity, kg, round=False, raise_if_failure=False)
                for move in moves)

        for mo in self:
            company = mo.company_id
            ffb = kg_of(mo.move_raw_ids.filtered(
                lambda m: m.product_id == company.ss_ffb_product_id))
            cpo = kg_of(mo.move_finished_ids.filtered(
                lambda m: m.product_id == company.ss_cpo_product_id))
            kernel = kg_of(mo.move_finished_ids.filtered(
                lambda m: m.product_id == company.ss_kernel_product_id))
            mo.ss_ffb_kg, mo.ss_cpo_kg, mo.ss_kernel_kg = ffb, cpo, kernel
            mo.ss_oer = 100.0 * cpo / ffb if ffb else 0.0
            mo.ss_ker = 100.0 * kernel / ffb if ffb else 0.0
