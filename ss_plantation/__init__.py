from . import controllers
from . import models
from . import report
from . import wizard


def post_init_hook(env):
    """Give every company working defaults for the plantation settings."""
    _create_default_bom(env)
    env['ss.plantation.yield.report'].init()  # the block cost-centre plan exists now
    ref = env.ref
    for company in env['res.company'].search([]):
        warehouse = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        company.write({k: v for k, v in {
            'ss_ffb_product_id': ref('ss_plantation.product_ffb').id,
            'ss_cpo_product_id': ref('ss_plantation.product_cpo').id,
            'ss_kernel_product_id': ref('ss_plantation.product_kernel').id,
            'ss_consumption_location_id': ref('ss_plantation.location_consumption').id,
            'ss_estate_location_id': ref('ss_plantation.location_estate_harvest').id,
            'ss_warehouse_id': warehouse.id,
        }.items() if not company[k]})


def _create_default_bom(env):
    """Typical oil palm yields per 1,000 kg of FFB: ~22% oil, ~5% kernel, ~6% shell."""
    cpo = env.ref('ss_plantation.product_cpo')
    if env['mrp.bom'].search_count([('product_tmpl_id', '=', cpo.product_tmpl_id.id)], limit=1):
        return
    kg = env.ref('uom.product_uom_kgm')
    env['mrp.bom'].create({
        'product_tmpl_id': cpo.product_tmpl_id.id,
        'product_qty': 220,
        'uom_id': kg.id,
        'bom_line_ids': [(0, 0, {
            'product_id': env.ref('ss_plantation.product_ffb').id,
            'product_qty': 1000,
            'uom_id': kg.id,
        })],
        'byproduct_ids': [
            (0, 0, {'product_id': env.ref('ss_plantation.product_kernel').id,
                    'product_qty': 50, 'uom_id': kg.id}),
            (0, 0, {'product_id': env.ref('ss_plantation.product_shell').id,
                    'product_qty': 60, 'uom_id': kg.id}),
        ],
    })
