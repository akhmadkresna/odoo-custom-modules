from odoo import Command
from odoo.addons.base.tests.common import BaseCommon


class SsPlantationCommon(BaseCommon):
    _test_user_groups = (
        'ss_plantation.group_plantation_manager',
        'ss_plantation.group_ss_feature_payroll',
        'ss_plantation.group_ss_feature_mill',
        'ss_plantation.group_ss_feature_asset',
        'hr.group_hr_manager',
        'stock.group_stock_manager',
        'purchase.group_purchase_manager',
        'mrp.group_mrp_manager',
        'account.group_account_manager',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.store = cls.env['stock.location'].create({
            'name': 'Division store',
            'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id,
        })
        cls.estate = cls.env['ss.plantation.estate'].create({'name': 'Estate', 'code': 'E1'})
        cls.division = cls.env['ss.plantation.division'].create({
            'name': 'Afdeling I', 'code': 'D1', 'estate_id': cls.estate.id,
            'store_location_id': cls.store.id,
        })
        cls.block = cls._make_block('TA01', 20.0)
        cls.block_b = cls._make_block('TA02', 20.0)
        cls.harvester = cls.env['hr.employee'].create({'name': 'Harvester 1'})
        cls.harvester_2 = cls.env['hr.employee'].create({'name': 'Harvester 2'})
        cls.ffb = cls.company.ss_ffb_product_id
        cls.supplier = cls.env['res.partner'].create({'name': 'Smallholder'})

    @classmethod
    def _make_block(cls, code, bjr, stage='mature'):
        return cls.env['ss.plantation.block'].create({
            'name': 'Block ' + code, 'code': code, 'division_id': cls.division.id,
            'area_ha': 25.0, 'avg_bunch_weight_kg': bjr, 'stage': stage,
        })

    @classmethod
    def _make_tally(cls, lines, date=None, confirm=True):
        tally = cls.env['ss.plantation.harvest.tally'].create({
            'division_id': cls.division.id,
            **({'date': date} if date else {}),
            'line_ids': [Command.create(vals) for vals in lines],
        })
        if confirm:
            tally.action_confirm()
        return tally
