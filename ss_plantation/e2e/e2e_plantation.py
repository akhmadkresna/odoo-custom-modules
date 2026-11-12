"""End-to-end test of ss_plantation on the KPM dev server via JSON-2.

Company 2 (My Indonesian Company, IDR). Master data is created only if missing; transactions are
created once (tagged E2E). Every step prints OK/FAIL and the script continues where independent.
"""
import json, sys, traceback
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from kpm import call, sr, one, OdooError

CO = int(__import__('os').environ.get('E2E_COMPANY', 2))  # the Indonesian (IDR) company
CTX = {'allowed_company_ids': sorted({CO, 1})}
D1, D2 = '2026-11-02', '2026-11-03'
PERIOD = ('2026-11-01', '2026-11-30')
S = {}          # ids created / found
RESULTS = []


def c(model, method, ids=None, **kw):
    return call(model, method, ids=ids, context=kw.pop('context', CTX), **kw)


def create(model, vals, context=None):
    return c(model, 'create', vals_list=[vals], context=context or CTX)[0]


def get_or_create(model, domain, vals, context=None):
    found = c(model, 'search', domain=domain, limit=1)
    if found:
        return found[0]
    return create(model, vals, context)


def step(name):
    def deco(fn):
        try:
            out = fn()
            RESULTS.append((name, 'OK', out))
            print(f"[OK]   {name}" + (f" -> {out}" if out is not None else ''))
        except Exception as exc:  # noqa
            RESULTS.append((name, 'FAIL', str(exc)))
            print(f"[FAIL] {name}: {exc}")
        return fn
    return deco


def poly(lon, lat, d=0.003):
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


# ----------------------------------------------------------------------------------------------
# 1. CONFIGURATION
# ----------------------------------------------------------------------------------------------
@step("1.1 Warehouse for company 2 + plantation settings")
def _():
    wh = get_or_create('stock.warehouse', [['company_id', '=', CO]],
                       {'name': 'Plantation Warehouse', 'code': 'PLW', 'company_id': CO})
    S['wh'] = wh
    lot_stock = sr('stock.warehouse', [['id', '=', wh]], ['lot_stock_id'], context=CTX)[0]['lot_stock_id'][0]
    S['lot_stock'] = lot_stock
    def ref(name):
        data = sr('ir.model.data', [['module', '=', 'ss_plantation'], ['name', '=', name]], ['res_id'])
        return data[0]['res_id']
    c('res.company', 'write', ids=[CO], vals={
        'ss_warehouse_id': wh, 'ss_freshness_hours': 8,
        'ss_estate_location_id': ref('location_estate_harvest'),
        'ss_consumption_location_id': ref('location_consumption'),
        # a company created after the module was installed has no product defaults yet
        'ss_ffb_product_id': ref('product_ffb'), 'ss_cpo_product_id': ref('product_cpo'),
        'ss_kernel_product_id': ref('product_kernel')})
    S['kg'] = sr('ir.model.data', [['module', '=', 'uom'], ['name', '=', 'product_uom_kgm']], ['res_id'])[0]['res_id']
    return f"warehouse {wh}, stock loc {lot_stock}"


@step("1.2 Input store location (division store)")
def _():
    view = sr('stock.warehouse', [['id', '=', S['wh']]], ['view_location_id'], context=CTX)[0]['view_location_id'][0]
    S['store'] = get_or_create('stock.location', [['name', '=', 'Estate Input Store'], ['company_id', '=', CO]],
                               {'name': 'Estate Input Store', 'usage': 'internal', 'location_id': view, 'company_id': CO})
    return S['store']


@step("1.3 Harvest pay schemes (piece rate / mixed / daily)")
def _():
    S['sch_piece'] = get_or_create('ss.plantation.pay.scheme', [['name', '=', 'Piece Rate (Rp 120/kg)'], ['company_id', '=', CO]], {
        'name': 'Piece Rate (Rp 120/kg)', 'company_id': CO, 'mode': 'piece_rate', 'rate_per_kg': 120,
        'penalty_unripe': 2000, 'penalty_loose_left': 500})
    S['sch_mixed'] = get_or_create('ss.plantation.pay.scheme', [['name', '=', 'Mixed (basis 1000 kg + Rp 250/kg)'], ['company_id', '=', CO]], {
        'name': 'Mixed (basis 1000 kg + Rp 250/kg)', 'company_id': CO, 'mode': 'mixed', 'basis_kg': 1000, 'bonus_per_kg': 250,
        'penalty_unripe': 2000, 'penalty_loose_left': 500})
    S['sch_daily'] = get_or_create('ss.plantation.pay.scheme', [['name', '=', 'Daily Wage (penalties only)'], ['company_id', '=', CO]], {
        'name': 'Daily Wage (penalties only)', 'company_id': CO, 'mode': 'daily',
        'penalty_unripe': 2000, 'penalty_loose_left': 500})
    return {k: v for k, v in S.items() if k.startswith('sch_')}


@step("1.4 Assign pay schemes to employees (Siti=piece, Agus=mixed, Dewi=daily)")
def _():
    names = {'siti': 'Siti Rahayu', 'agus': 'Agus Pratama', 'dewi': 'Dewi Lestari', 'budi': 'Budi Santoso'}
    S['emp'] = {key: get_or_create('hr.employee', [['name', '=', name], ['company_id', '=', CO]],
                                   {'name': name, 'company_id': CO}) for key, name in names.items()}
    c('hr.employee', 'write', ids=[S['emp']['siti']], vals={'ss_pay_scheme_id': S['sch_piece']})
    c('hr.employee', 'write', ids=[S['emp']['agus']], vals={'ss_pay_scheme_id': S['sch_mixed']})
    c('hr.employee', 'write', ids=[S['emp']['dewi']], vals={'ss_pay_scheme_id': S['sch_daily']})


@step("1.5 FFB reference prices (general + tag 'Smallholder')")
def _():
    tag = get_or_create('res.partner.category', [['name', '=', 'Smallholder']], {'name': 'Smallholder'})
    S['tag'] = tag
    get_or_create('ss.plantation.ffb.price', [['company_id', '=', CO], ['partner_category_id', '=', False]],
                  {'company_id': CO, 'date_from': '2026-10-01', 'price_per_kg': 2400})
    get_or_create('ss.plantation.ffb.price', [['company_id', '=', CO], ['partner_category_id', '=', tag]],
                  {'company_id': CO, 'date_from': '2026-10-01', 'price_per_kg': 2600, 'partner_category_id': tag})


@step("1.6 Estate / division / blocks (company 2)")
def _():
    lon0, lat0 = 113.060, -1.510
    est = get_or_create('ss.plantation.estate', [['code', '=', 'E2E'], ['company_id', '=', CO]],
                        {'name': 'E2E Estate (Indonesia)', 'code': 'E2E', 'company_id': CO,
                         'boundary_geojson': poly(lon0 - 0.001, lat0 - 0.001, 0.014)})
    div = get_or_create('ss.plantation.division', [['code', '=', 'E-D1'], ['estate_id', '=', est]],
                        {'name': 'E2E Division 1', 'code': 'E-D1', 'estate_id': est, 'store_location_id': S['store'],
                         'boundary_geojson': poly(lon0 - 0.0005, lat0 - 0.0005, 0.010)})
    S['est'], S['div'] = est, div
    specs = [('E101', 'mature', 2012), ('E102', 'mature', 2013), ('E103', 'mature', 2014),
             ('E104', 'mature', 2015), ('E105', 'immature', 2023), ('E106', 'replanting', 2025)]
    S['blk'] = {}
    for i, (code, stage, yr) in enumerate(specs):
        row, col = divmod(i, 3)
        S['blk'][code] = get_or_create('ss.plantation.block', [['code', '=', code], ['division_id', '=', div]], {
            'name': f'Block {code}', 'code': code, 'division_id': div, 'area_ha': 11.0,
            'planting_date': f'{yr}-03-01', 'stage': stage, 'variety': 'Tenera DxP', 'stand_count': 1540,
            'avg_bunch_weight_kg': 14.5 if stage == 'mature' else 0,
            'boundary_geojson': poly(lon0 + col * 0.003, lat0 + row * 0.003)})
    return S['blk']


@step("1.7 Landmarks for the estate (mill, weighbridge)")
def _():
    types = {t['name']: t['id'] for t in sr('ss.plantation.landmark.type', [], ['name'])}
    for name, tn, lon, lat in [('E2E Mill', 'Mill', 113.075, -1.5035), ('E2E Weighbridge', 'Weighbridge', 113.072, -1.5035)]:
        get_or_create('ss.plantation.landmark', [['name', '=', name]], {
            'name': name, 'type_id': types[tn], 'estate_id': S['est'], 'company_id': CO,
            'geometry_geojson': json.dumps({"type": "Point", "coordinates": [lon, lat]})})


@step("1.8 Products: NPK fertilizer (storable, kg) + opening stock in input store")
def _():
    prod = get_or_create('product.product', [['name', '=', 'E2E NPK Fertilizer']], {
        'name': 'E2E NPK Fertilizer', 'type': 'consu', 'is_storable': True, 'uom_id': S['kg']})
    S['npk'] = prod
    quant = c('stock.quant', 'create', vals_list=[{'product_id': prod, 'location_id': S['store'],
                                                 'inventory_quantity': 1000}],
              context={**CTX, 'inventory_mode': True})[0]
    c('stock.quant', 'action_apply_inventory', ids=[quant], context={**CTX, 'inventory_mode': True})
    return f"product {prod}, quant {quant}"


@step("1.9 Partners: smallholder supplier (tag) + buyer")
def _():
    S['sup'] = get_or_create('res.partner', [['name', '=', 'E2E Smallholder Pak Joko']], {
        'name': 'E2E Smallholder Pak Joko', 'category_id': [[4, S['tag']]], 'supplier_rank': 1})
    S['buyer'] = get_or_create('res.partner', [['name', '=', 'E2E PT Pembeli TBS']], {
        'name': 'E2E PT Pembeli TBS', 'customer_rank': 1})


# ----------------------------------------------------------------------------------------------
# 2. TRANSACTIONS
# ----------------------------------------------------------------------------------------------
@step("2.1 Field activity: fertilising block E101 with 200 kg NPK -> Done (stock move)")
def _():
    act_type = one('ss.plantation.activity.type', [['code', '=', 'FERT']], ['id'])['id']
    act = create('ss.plantation.activity', {
        'date': D1, 'block_id': S['blk']['E101'], 'type_id': act_type, 'quantity': 11.0, 'man_days': 6,
        'company_id': CO, 'employee_ids': [[6, 0, [S['emp']['budi']]]], 'note': 'E2E fertilising',
        'input_line_ids': [[0, 0, {'product_id': S['npk'], 'qty': 200}]]})
    c('ss.plantation.activity', 'action_done', ids=[act])
    S['act'] = act
    state = sr('ss.plantation.activity', [['id', '=', act]], ['state', 'name'], context=CTX)[0]
    return state


@step("2.2 Harvest tallies day 1 + day 2 -> Confirm")
def _():
    def line(block, emp, ripe, unripe=0, over=0, loose=0, left=0):
        return [0, 0, {'block_id': S['blk'][block], 'harvester_id': S['emp'][emp], 'bunches_ripe': ripe,
                       'bunches_unripe': unripe, 'bunches_overripe': over, 'loose_fruit_kg': loose, 'loose_left_kg': left}]
    def tally(date, lines):  # re-runs reuse the day's tally instead of colliding with it
        return get_or_create('ss.plantation.harvest.tally', [
            ['date', '=', date], ['division_id', '=', S['div']], ['company_id', '=', CO], ['state', '!=', 'cancel']], {
            'date': date, 'division_id': S['div'], 'company_id': CO, 'clerk_id': S['emp']['budi'], 'line_ids': lines})
    t1 = tally(D1, [line('E101', 'agus', 90, unripe=3, left=2), line('E102', 'siti', 100, over=5, loose=20),
                    line('E103', 'dewi', 80, unripe=6, left=3)])
    t2 = tally(D2, [line('E101', 'agus', 70), line('E104', 'siti', 110, loose=15), line('E102', 'dewi', 60)])
    c('ss.plantation.harvest.tally', 'action_confirm', ids=[t for t in (t1, t2) if sr(
        'ss.plantation.harvest.tally', [['id', '=', t], ['state', '=', 'draft']], ['id'], context=CTX)])
    S['tallies'] = [t1, t2]
    return sr('ss.plantation.harvest.tally', [['id', 'in', [t1, t2]]], ['name', 'state', 'bunch_total', 'est_weight_kg'], context=CTX)


@step("2.3 Transport note (day 2 harvest) -> Send")
def _():
    t = get_or_create('ss.plantation.transport', [['date', '=', D2], ['plate', '=', 'KT 1234 AB'], ['company_id', '=', CO],
                                                   ['state', '!=', 'cancel']], {
        'date': D2, 'harvested_at': '2026-11-03 06:30:00', 'division_id': S['div'], 'company_id': CO,
        'plate': 'KT 1234 AB', 'driver_id': S['emp']['budi'],
        'line_ids': [[0, 0, {'block_id': S['blk']['E101'], 'bunches': 190}],
                     [0, 0, {'block_id': S['blk']['E104'], 'bunches': 150}]]})
    if sr('ss.plantation.transport', [['id', '=', t], ['state', '=', 'draft']], ['id'], context=CTX):
        c('ss.plantation.transport', 'action_send', ids=[t])
    S['transport'] = t
    return sr('ss.plantation.transport', [['id', '=', t]], ['name', 'state', 'bunch_total', 'est_weight_kg'], context=CTX)


@step("2.4 Weigh ticket: own estate -> mill (grade deductions, transport link) -> Confirm")
def _():
    grade = {g['name']: g['id'] for g in sr('ss.plantation.grade.type', [], ['name'])}
    tk = create('ss.plantation.weigh.ticket', {
        'date': D2, 'company_id': CO, 'direction': 'estate_in', 'plate': 'KT 1234 AB', 'driver_name': 'Budi Santoso',
        'weigh_in_at': '2026-11-03 10:30:00', 'weigh_out_at': '2026-11-03 10:45:00',
        'gross_kg': 12000, 'tare_kg': 7000, 'transport_ids': [[4, S['transport']]],
        'grade_line_ids': [[0, 0, {'grade_type_id': grade['Unripe Bunches'], 'percent': 2}],
                           [0, 0, {'grade_type_id': grade['Dirt and Water'], 'kg': 25}]]})
    S['tk_estate'] = tk
    pre = sr('ss.plantation.weigh.ticket', [['id', '=', tk]], ['name', 'net_kg', 'deduction_kg', 'payable_kg', 'delay_hours', 'too_stale'], context=CTX)[0]
    c('ss.plantation.weigh.ticket', 'action_confirm', ids=[tk])
    post = sr('ss.plantation.weigh.ticket', [['id', '=', tk]], ['state', 'lot_id', 'picking_id'], context=CTX)[0]
    S['lot_estate'] = post['lot_id'][0] if post['lot_id'] else None
    return {**pre, **post}


@step("2.5 Weigh ticket: bought from smallholder (tag price) -> Confirm (PO + receipt)")
def _():
    tk = create('ss.plantation.weigh.ticket', {
        'date': D2, 'company_id': CO, 'direction': 'third_party_in', 'partner_id': S['sup'], 'plate': 'KT 9876 CD',
        'weigh_in_at': '2026-11-03 11:00:00', 'gross_kg': 8000, 'tare_kg': 4500})
    S['tk_third'] = tk
    pre = sr('ss.plantation.weigh.ticket', [['id', '=', tk]], ['name', 'payable_kg', 'unit_price', 'amount_total'], context=CTX)[0]
    c('ss.plantation.weigh.ticket', 'action_confirm', ids=[tk])
    post = sr('ss.plantation.weigh.ticket', [['id', '=', tk]], ['state', 'purchase_id', 'picking_id'], context=CTX)[0]
    return {**pre, **post}


@step("2.6 Weigh ticket: sale of FFB lot to buyer -> Confirm (delivery)")
def _():
    tk = create('ss.plantation.weigh.ticket', {
        'date': D2, 'company_id': CO, 'direction': 'out', 'partner_id': S['buyer'], 'plate': 'KT 5555 EF',
        'gross_kg': 6000, 'tare_kg': 3000, 'unit_price': 2800, 'source_lot_id': S['lot_estate']})
    S['tk_sale'] = tk
    c('ss.plantation.weigh.ticket', 'action_confirm', ids=[tk])
    return sr('ss.plantation.weigh.ticket', [['id', '=', tk]], ['name', 'state', 'payable_kg', 'amount_total', 'picking_id'], context=CTX)


@step("2.7 Mill: BoM (FFB -> CPO + kernel) + manufacturing order -> Done (OER / KER)")
def _():
    co = sr('res.company', [['id', '=', CO]], ['ss_ffb_product_id', 'ss_cpo_product_id', 'ss_kernel_product_id'], context=CTX)[0]
    ffb, cpo, ker = co['ss_ffb_product_id'][0], co['ss_cpo_product_id'][0], co['ss_kernel_product_id'][0]
    bom = c('mrp.bom', 'create', vals_list=[{
        'product_tmpl_id': sr('product.product', [['id', '=', cpo]], ['product_tmpl_id'], context=CTX)[0]['product_tmpl_id'][0],
        'product_qty': 440, 'uom_id': S['kg'], 'company_id': CO, 'type': 'normal',  # uom 16 = kg
        'bom_line_ids': [[0, 0, {'product_id': ffb, 'product_qty': 2000}]],
        'byproduct_ids': [[0, 0, {'product_id': ker, 'product_qty': 100}]]}], context=CTX)[0]
    S['bom'] = bom
    mo = create('mrp.production', {'product_id': cpo, 'bom_id': bom, 'product_qty': 440, 'uom_id': S['kg'], 'company_id': CO})
    S['mo'] = mo
    c('mrp.production', 'action_confirm', ids=[mo])
    c('mrp.production', 'action_assign', ids=[mo])
    mo_data = sr('mrp.production', [['id', '=', mo]], ['name', 'state', 'reservation_state'], context=CTX)[0]
    c('mrp.production', 'write', ids=[mo], vals={'qty_producing': 440})
    res = c('mrp.production', 'button_mark_done', ids=[mo],
            context={**CTX, 'skip_consumption': True, 'skip_backorder': True, 'skip_immediate': True})
    return {**mo_data, 'mark_done_returned': (res if isinstance(res, dict) and res.get('res_model') else 'ok')}


# ----------------------------------------------------------------------------------------------
# 3. PAYROLL
# ----------------------------------------------------------------------------------------------
@step("3.1 Compute Harvest Pay wizard (Nov 2026) -> Compute")
def _():
    w = create('ss.plantation.harvest.pay.wizard', {'date_from': PERIOD[0], 'date_to': PERIOD[1]})
    c('ss.plantation.harvest.pay.wizard', 'action_compute', ids=[w])
    pays = sr('ss.plantation.harvest.pay', [['date_from', '=', PERIOD[0]], ['company_id', '=', CO]],
              ['employee_id', 'scheme_id', 'harvested_kg', 'bonus_amount', 'penalty_amount', 'amount', 'state'], context=CTX)
    S['pays'] = [p['id'] for p in pays]
    return pays


@step("3.2 Payslips: create, 'Add Harvest Pay', compute sheet")
def _():
    out = []
    for key in ('siti', 'agus', 'dewi'):
        emp = S['emp'][key]
        slip = create('hr.payslip', {'employee_id': emp, 'date_from': PERIOD[0], 'date_to': PERIOD[1], 'company_id': CO})
        c('hr.payslip', 'action_ss_add_harvest_pay', ids=[slip])
        c('hr.payslip', 'compute_sheet', ids=[slip])
        lines = sr('hr.payslip.line', [['slip_id', '=', slip]], ['code', 'name', 'total'], context=CTX)
        harvest = [l for l in lines if l['code'] == 'SS_HARVEST']
        net = [l for l in lines if l['code'] in ('NET', 'THP')]
        out.append({'employee': key, 'slip': slip, 'harvest_line': harvest[0]['total'] if harvest else None,
                    'net': net[0]['total'] if net else None, 'lines': len(lines)})
    S['slips'] = out
    return out


@step("3.3 Tiered premium and Sunday factor: scheme -> Sunday + Monday tallies -> Compute -> check amounts")
def _():
    sch = get_or_create('ss.plantation.pay.scheme', [['name', '=', 'Tiered (basis 1000, Rp 250, Rp 350 beyond 500 kg, Sunday x2)'], ['company_id', '=', CO]], {
        'name': 'Tiered (basis 1000, Rp 250, Rp 350 beyond 500 kg, Sunday x2)', 'company_id': CO, 'mode': 'mixed',
        'basis_kg': 1000, 'bonus_per_kg': 250, 'holiday_factor': 2.0,
        'tier_ids': [[0, 0, {'above_kg': 500, 'rate_per_kg': 350}]]})
    rina = get_or_create('hr.employee', [['name', '=', 'Rina Wulandari'], ['company_id', '=', CO]],
                         {'name': 'Rina Wulandari', 'company_id': CO})
    c('hr.employee', 'write', ids=[rina], vals={'ss_pay_scheme_id': sch})
    sunday, monday = '2026-11-08', '2026-11-09'

    def tally(date, bunches):
        return get_or_create('ss.plantation.harvest.tally', [
            ['date', '=', date], ['division_id', '=', S['div']], ['company_id', '=', CO], ['state', '!=', 'cancel']], {
            'date': date, 'division_id': S['div'], 'company_id': CO, 'clerk_id': S['emp']['budi'],
            'line_ids': [[0, 0, {'block_id': S['blk']['E101'], 'harvester_id': rina, 'bunches_ripe': bunches}]]})
    t = [tally(sunday, 100), tally(monday, 140)]
    pending = [x for x in t if sr('ss.plantation.harvest.tally', [['id', '=', x], ['state', '=', 'draft']], ['id'], context=CTX)]
    if pending:
        c('ss.plantation.harvest.tally', 'action_confirm', ids=pending)
    w = create('ss.plantation.harvest.pay.wizard', {'date_from': sunday, 'date_to': monday, 'employee_ids': [[6, 0, [rina]]]})
    c('ss.plantation.harvest.pay.wizard', 'action_compute', ids=[w])
    pay = sr('ss.plantation.harvest.pay', [['employee_id', '=', rina], ['date_from', '=', sunday], ['date_to', '=', monday]],
             ['harvested_kg', 'bonus_amount', 'amount'], context=CTX)[0]
    # Sunday: 1,450 kg, 450 kg above basis x Rp 250 x 2 = 225,000
    # Monday: 2,030 kg, 1,030 above basis = 500 x 250 + 530 x 350 = 310,500
    expected = 225000.0 + 310500.0
    if abs(pay['bonus_amount'] - expected) > 0.5:
        raise AssertionError(f"bonus {pay['bonus_amount']} but expected {expected}")
    return {'kg': pay['harvested_kg'], 'bonus': pay['bonus_amount'], 'expected': expected}


# ----------------------------------------------------------------------------------------------
# 4. ASSET + REPORT
# ----------------------------------------------------------------------------------------------
@step("4.1 Capitalise mature block E102 as asset (wizard)")
def _():
    done = sr('ss.plantation.block', [['id', '=', S['blk']['E102']]], ['asset_id', 'cost_total'], context=CTX)[0]
    if done['asset_id']:  # re-run: the block was capitalised already
        return {'already capitalised': done['asset_id']}
    only = {'allowed_company_ids': [CO]}  # accounts of the Indonesian company only
    fixed = sr('account.account', [['account_type', '=', 'asset_fixed']], ['code', 'name', 'depreciation_model_id'], context=only, limit=20)
    pick = next((a for a in fixed if 'Plantation' in a['name'] or 'Machinery' in a['name']), fixed[0])
    if not pick['depreciation_model_id']:  # a fixed-asset account needs a depreciation model before a block can use it
        model = one('account.depreciation.model', [['name', '=', '16 Year']], ['id'])
        c('account.account', 'write', ids=[pick['id']], vals={'depreciation_model_id': model['id']}, context=only)
    counter = sr('account.account', [['account_type', '=', 'asset_current']], ['code', 'name'], context=only, limit=1)[0]
    journal = one('account.journal', [['company_id', '=', CO], ['type', '=', 'general'], ['code', '=', 'MISC']], ['id'])['id']
    w = create('ss.plantation.block.asset.wizard', {
        'block_id': S['blk']['E102'], 'name': 'Plantation E102', 'acquisition_date': '2026-11-04',
        'original_value': 250000000, 'account_asset_id': pick['id'], 'counterpart_account_id': counter['id'],
        'journal_id': journal})
    c('ss.plantation.block.asset.wizard', 'action_create_asset', ids=[w])
    blk = sr('ss.plantation.block', [['id', '=', S['blk']['E102']]], ['asset_id', 'cost_total'], context=CTX)[0]
    return {'asset_account': pick, 'counterpart': counter, **blk}


@step("4.2 Yield and Cost report (month x division)")
def _():
    rows = c('ss.plantation.yield.report', 'search_read', domain=[['estate_id', '=', S['est']]],
             fields=['month', 'division_id', 'block_id', 'bunches', 'est_weight_kg', 'weighed_kg', 'cost'])
    return rows[:6] if rows else 'empty'


@step("4.3 Extraction rates on the manufacturing order")
def _():
    return sr('mrp.production', [['id', '=', S['mo']]], ['name', 'state', 'ss_ffb_kg', 'ss_cpo_kg', 'ss_kernel_kg', 'ss_oer', 'ss_ker'], context=CTX)


print("\n==== SUMMARY ====")
for name, st, _out in RESULTS:
    print(f"{st:5} {name}")
json.dump(S, open('e2e_state.json', 'w'), indent=1, default=str)
