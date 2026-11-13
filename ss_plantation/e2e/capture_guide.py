"""Capture the stills of the Indonesian process guide on a live instance.

    ./run_capture.sh OUT_DIR            (reads the KPM_SS_* entries of credentials.env)

Writes figNN.png files named after the figure number in the guide. Needs the API key to look up
which records to open. Run e2e_plantation.py first so the data exists. The phone figures (24 to 29)
come from offline_field.py. Env: ODOO_URL, API_URL, ODOO_DB, ODOO_LOGIN, ODOO_PW, ODOO_API_KEY, E2E_COMPANY.
"""
import json, os, re, sys, urllib.request
from playwright.sync_api import sync_playwright

URL, DB, KEY = os.environ['ODOO_URL'], os.environ['ODOO_DB'], os.environ['ODOO_API_KEY']
LOGIN, PW, CO = os.environ['ODOO_LOGIN'], os.environ['ODOO_PW'], int(os.environ.get('E2E_COMPANY', 3))
OUT = sys.argv[1] if len(sys.argv) > 1 else 'guide_out'
ONLY = set(filter(None, os.environ.get('ONLY', '').split(',')))  # e.g. ONLY=01,20 captures just those figures
os.makedirs(OUT, exist_ok=True)
CTX = {'allowed_company_ids': sorted({1, CO}), 'active_test': False}

# labels of the Indonesian interface come from the module's own translations
_T = {}
_txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'i18n', 'id.po'), encoding='utf-8').read()
_j = lambda x: ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', x))
for a, b in re.findall(r'msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)msgstr ((?:"(?:[^"\\]|\\.)*"\s*)+)', _txt):
    if _j(a): _T[_j(a)] = _j(b)
t = lambda s: _T.get(s, s)


def rpc(model, method, **kw):
    req = urllib.request.Request(f'{os.environ["API_URL"]}/json/2/{model}/{method}', data=json.dumps({**kw, 'context': CTX}).encode(),
                                 headers={'Authorization': 'bearer ' + KEY, 'X-Odoo-Database': DB, 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=60))


def first(model, domain, fields, order='id desc'):
    rows = rpc(model, 'search_read', domain=domain, fields=fields, order=order, limit=1)
    if not rows:
        raise RuntimeError(f'no {model} for {domain}')
    return rows[0]


ok, bad = [], []


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1600, 'height': 900})
        pg = ctx.new_page()
        pg.goto(URL + '/web/login'); pg.fill('input[name=login]', LOGIN); pg.fill('input[name=password]', PW)
        pg.click('button[type=submit]'); pg.wait_for_selector('.o_navbar', timeout=60000)
        ctx.add_cookies([{'name': 'cids', 'value': str(CO), 'url': URL}])

        def settle(ms=1800):
            pg.wait_for_timeout(ms)

        def open_app():
            pg.goto(URL + '/odoo'); pg.wait_for_selector('.o_app', timeout=60000)
            pg.locator('.o_app', has_text=t('Plantation')).first.click(); pg.wait_for_selector('.o_menu_sections', timeout=30000); settle(2500)

        def menu(top, item=None):
            pg.locator('.o_menu_sections').get_by_text(t(top), exact=True).first.click()
            if item:
                pg.locator('.dropdown-menu .dropdown-item').filter(has_text=re.compile('^\\s*' + re.escape(t(item)) + '\\s*$')).first.click()
            settle()

        def row(text):
            pg.locator('.o_data_row', has_text=text).first.click(); pg.wait_for_selector('.o_form_view'); settle(2200)

        def close_dialog():
            for sel in ('.modal footer button.btn-secondary', '.modal .btn-close'):
                if pg.locator(sel).count():
                    try: pg.locator(sel).first.click(timeout=2000); break
                    except Exception: pass
            settle(800)

        def fig(num, label, fn, wait=None):
            if ONLY and num not in ONLY:
                return
            try:
                open_app()
                fn()
                if wait:
                    pg.wait_for_selector(wait, timeout=30000)
                settle(1500)
                pg.screenshot(path=os.path.join(OUT, f'fig{num}.png'))
                ok.append(num); print('OK  ', num, label, flush=True)
            except Exception as e:
                bad.append(num); print('FAIL', num, label, str(e).splitlines()[0][:160], flush=True)
            for _ in range(2):
                close_dialog()

        # ---- data lookups
        estate = first('ss.plantation.estate', [['code', '=', 'SGR']], ['name'])
        division = first('ss.plantation.division', [['code', '=', 'AFD-I']], ['name'])
        block = first('ss.plantation.block', [['code', '=', 'E101']], ['name', 'code'])
        scheme_mixed = first('ss.plantation.pay.scheme', [['name', '=', 'Basis 1.000 kg + bonus Rp 250/kg']], ['name'])
        scheme_tier = first('ss.plantation.pay.scheme', [['name', 'ilike', 'Bertingkat']], ['name'])
        activity = first('ss.plantation.activity', [['state', '=', 'done'], ['company_id', '=', CO], ['input_line_ids', '!=', False]], ['name'])
        tally = first('ss.plantation.harvest.tally', [['date', '=', '2026-11-02'], ['company_id', '=', CO], ['state', '=', 'confirmed']], ['name'])
        note = first('ss.plantation.transport', [['state', '=', 'weighed'], ['company_id', '=', CO]], ['name'], order='id')
        t_estate = first('ss.plantation.weigh.ticket', [['direction', '=', 'estate_in'], ['state', '=', 'confirmed'], ['company_id', '=', CO]], ['name'], order='id')
        t_third = first('ss.plantation.weigh.ticket', [['direction', '=', 'third_party_in'], ['state', '=', 'confirmed'], ['company_id', '=', CO]], ['name'], order='id')
        t_sale = first('ss.plantation.weigh.ticket', [['direction', '=', 'out'], ['state', '=', 'confirmed'], ['company_id', '=', CO]], ['name'], order='id')
        slip = first('hr.payslip', [['state', '=', 'draft'], ['company_id', '=', CO], ['employee_id.name', '=', 'Agus Pratama'], ['date_from', '=', '2026-12-01']], ['name', 'employee_id'])
        print('records:', estate['name'], division['name'], block['code'], activity['name'], tally['name'], note['name'], t_estate['name'], t_third['name'], t_sale['name'], slip['id'], flush=True)

        def settings():
            menu('Configuration', 'Settings'); pg.wait_for_selector('.o_setting_box, .settings', timeout=30000); settle(4000)
            tab = pg.locator('.settings_tab .tab, .o_setting_tab').filter(has_text=re.compile(t('Plantation')))
            if tab.count(): tab.first.click(); settle(2000)

        def list_screen(top, item): return lambda: menu(top, item)

        fig('01', 'Pengaturan', settings)
        fig('02', 'Jenis aktivitas', list_screen('Configuration', 'Activity Types'), '.o_list_view')
        fig('03', 'Potongan mutu', list_screen('Configuration', 'Grade Deductions'), '.o_list_view')
        fig('04', 'Harga referensi', list_screen('Configuration', 'FFB Reference Prices'), '.o_list_view')
        fig('05', 'Skema campuran', lambda: (menu('Payroll', 'Pay Schemes'), row(scheme_mixed['name'])), '.o_form_view')
        fig('5b', 'Skema bertingkat', lambda: (menu('Payroll', 'Pay Schemes'), row('Bertingkat')), '.o_form_view .o_field_x2many')
        fig('06', 'Kebun', lambda: (menu('Master Data', 'Estates'), row(estate['name'])), '.o_form_view')
        fig('07', 'Divisi', lambda: (menu('Master Data', 'Divisions'), row(division['name'])), '.o_form_view')
        fig('08', 'Blok', lambda: (menu('Master Data', 'Blocks'), row(block['name'])), '.o_form_view')
        fig('09', 'Impor penanda lokasi', lambda: menu('Master Data', 'Import Landmarks'), '.modal')
        fig('10', 'Peta', lambda: (menu('Map'), pg.wait_for_selector('.leaflet-container', timeout=30000), settle(8000)), '.leaflet-container')
        fig('11', 'Aktivitas selesai', lambda: (menu('Operations', 'Field Activities'), row(activity['name'])), '.o_form_view')
        fig('12', 'Tally', lambda: (menu('Operations', 'Harvest Tally'), row(tally['name'])), '.o_form_view')
        fig('13', 'Nota angkut', lambda: (menu('Operations', 'Transport Notes'), row(note['name'])), '.o_form_view')

        def new_ticket():
            menu('Operations', 'Weigh Tickets'); pg.locator('.o_list_button_add').click(); pg.wait_for_selector('.o_form_view'); settle(2000)
        fig('14', 'Tiket baru', new_ticket, '.o_form_view')
        fig('15', 'Tiket kebun sendiri', lambda: (menu('Operations', 'Weigh Tickets'), row(t_estate['name'])), '.o_form_view')
        fig('16', 'Tiket beli', lambda: (menu('Operations', 'Weigh Tickets'), row(t_third['name'])), '.o_form_view')
        fig('17', 'Tiket jual', lambda: (menu('Operations', 'Weigh Tickets'), row(t_sale['name'])), '.o_form_view')
        fig('18', 'Rasio ekstraksi', list_screen('Mill', 'Extraction Rates'), '.o_pivot, .o_content')

        def compute_dialog():
            menu('Payroll', 'Compute Harvest Pay'); pg.wait_for_selector('.modal')
            for name, value in (('date_from', '01/12/2026'), ('date_to', '31/12/2026')):
                inp = pg.locator(f'.modal .o_field_widget[name={name}] input')
                if inp.count():
                    inp.first.fill(value); inp.first.press('Enter')
            settle(800)
        fig('19', 'Dialog hitung gaji panen', compute_dialog, '.modal')
        def harvest_pay_list():
            menu('Payroll', 'Harvest Pay'); pg.wait_for_selector('.o_list_view')
            pg.locator('.o_searchview_dropdown_toggler').first.click(); settle(800)
            pg.locator('.o_filter_menu .dropdown-item, .dropdown-menu .o_menu_item').filter(has_text=re.compile('^\\s*' + re.escape(t('Draft')) + '\\s*$')).first.click(); settle(1500)
            pg.keyboard.press('Escape'); settle(800)
        fig('20', 'Gaji panen', harvest_pay_list, '.o_list_view')
        fig('21', 'Slip gaji', lambda: pg.goto(f'{URL}/odoo/hr.payslip/{slip["id"]}'), '.o_form_view')

        def capitalise():
            menu('Master Data', 'Blocks'); row(block['name'])
            pg.get_by_role('button', name=t('Capitalise as Asset')).click(); pg.wait_for_selector('.modal'); settle(1500)
        fig('22', 'Dialog kapitalisasi', capitalise, '.modal')
        fig('23', 'Hasil dan biaya', list_screen('Reporting', 'Yield and Cost'), '.o_pivot, .o_content')
        b.close()
    print('captured', len(ok), 'failed', bad)
    sys.exit(1 if bad else 0)


main()
