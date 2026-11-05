"""Playwright UI end-to-end run of ss_plantation. Writes numbered PNG stills and results.json to OUT dir.
Usage: ODOO_URL=... ODOO_LOGIN=... ODOO_PW=... python3 ui_plantation.py OUT_DIR"""
import json, os, re, sys, time, traceback
from playwright.sync_api import sync_playwright

URL = os.environ.get('ODOO_URL', 'https://odoo20.kpmgroup.co.id')
LOGIN = os.environ.get('ODOO_LOGIN', 'dev@kpmgroup.co.id')
PW = os.environ['ODOO_PW']
OUT = sys.argv[1] if len(sys.argv) > 1 else 'ui_out'
os.makedirs(OUT, exist_ok=True)
results, errors, n = [], [], [0]

LANGMODE = os.environ.get('LANGMODE', 'en')  # 'id' = run the Indonesian UI; labels are read from i18n/id.po
_T = {}
if LANGMODE == 'id':
    import re
    _po = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'i18n', 'id.po')
    _txt = open(_po, encoding='utf-8').read()
    def _j(x): return ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', x))
    for a, b in re.findall(r'msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)msgstr ((?:"(?:[^"\\]|\\.)*"\s*)+)', _txt):
        if _j(a): _T[_j(a)] = _j(b)
def t(s): return _T.get(s, s)



def settle(pg, ms=1500):
    pg.wait_for_timeout(ms)


def shot(pg, title):
    n[0] += 1
    f = f"{n[0]:02d}_{''.join(c if c.isalnum() else '_' for c in title.lower())[:50]}.png"
    pg.screenshot(path=os.path.join(OUT, f))
    return f


def step(pg, title, fn, expect=None, note=''):
    status, detail = 'PASS', ''
    before = len(errors)
    try:
        fn()
        settle(pg)
        if pg.locator('.o_error_dialog, .modal .o_error_dialog').count():
            status, detail = 'FAIL', 'Odoo error dialog: ' + pg.locator('.modal-body').first.inner_text()[:300]
        elif expect and pg.locator(expect).count() == 0:
            status, detail = 'FAIL', f'expected element not found: {expect}'
    except Exception as e:
        status, detail = 'FAIL', str(e).splitlines()[0][:300]
    if len(errors) > before and status == 'PASS':
        detail = 'console errors: ' + ' | '.join(errors[before:])[:300]
    f = shot(pg, title)
    results.append({'step': title, 'status': status, 'detail': detail, 'shot': f, 'note': note})
    print(status, title, detail)
    # clear dialogs
    for sel in ('.modal .btn-close', '.modal-footer .btn-secondary'):
        if pg.locator(sel).count():
            try: pg.locator(sel).first.click(timeout=2000)
            except Exception: pass


def menu(pg, top, item=None):
    pg.locator('.o_menu_sections').get_by_text(t(top), exact=True).first.click()
    if item:
        pg.locator('.dropdown-menu .dropdown-item').filter(has_text=re.compile('^\\s*' + re.escape(t(item)) + '\\s*$')).first.click()
    settle(pg)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1600, 'height': 900})
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append(m.text[:150]) if m.type == 'error' and 'favicon' not in m.text else None)
    pg.on('pageerror', lambda e: errors.append('pageerror ' + str(e)[:150]))

    def login():
        pg.goto(URL + '/web/login'); pg.fill('input[name=login]', LOGIN); pg.fill('input[name=password]', PW)
        pg.click('button[type=submit]'); pg.wait_for_selector('.o_navbar', timeout=60000); settle(pg)
    step(pg, 'Login', login, '.o_navbar')

    step(pg, 'Home menu shows Plantation app', lambda: None, '.o_app:has-text("%s")' % t('Plantation'))
    step(pg, 'Open Plantation app (Dashboards)', lambda: pg.locator('.o_app', has_text=t('Plantation')).first.click(), '.o_menu_sections')
    pg.wait_for_timeout(4000)
    step(pg, 'Dashboards: spreadsheet dashboard renders', lambda: menu(pg, 'Dashboards'), '.o_action')

    def map_view():
        menu(pg, 'Map'); pg.wait_for_selector('.leaflet-container', timeout=30000); pg.wait_for_timeout(6000)
    step(pg, 'Map: Leaflet map with estate layers', map_view, '.leaflet-container',
         'Tiles from OpenStreetMap, blocks as polygons, landmarks as markers.')

    def map_layers():
        for sel in ('.leaflet-control-layers-toggle', '.leaflet-control-layers'):
            if pg.locator(sel).count():
                pg.locator(sel).first.hover(); break
        pg.wait_for_timeout(800)
    step(pg, 'Map: layer control', map_layers, '.leaflet-container')

    def map_click():
        paths = pg.locator('path.leaflet-interactive')
        if paths.count():
            paths.nth(min(3, paths.count() - 1)).click(force=True)
        pg.wait_for_timeout(1000)
    step(pg, 'Map: click a block shows popup', map_click, '.leaflet-container')

    def owner_dash():
        menu(pg, 'Dashboards'); pg.locator('.o_spreadsheet_dashboard_action, .o_search_panel, .o_action').first.wait_for()
        pg.get_by_text(t('Owner'), exact=True).first.click(); pg.wait_for_timeout(5000)
    step(pg, 'Dashboards: Plantation > Owner', owner_dash, '.o_action', 'Plantation dashboard group.')

    def to_company2():
        ctx.add_cookies([{'name': 'cids', 'value': '2', 'url': URL}])
        pg.goto(URL + '/odoo'); pg.wait_for_selector('.o_navbar'); settle(pg, 3000)
        pg.locator('.o_app', has_text=t('Plantation')).first.click(); settle(pg, 3000)
    step(pg, 'Switch to the E2E company (company 2) holding transactions', to_company2, '.o_navbar')

    def lst(top, item, title, expect_rows=True):
        def f(): menu(pg, top, item)
        step(pg, title, f, '.o_list_view, .o_kanban_view, .o_pivot, .o_graph_renderer, .o_form_view')

    def open_first(title):
        def f(): pg.locator('.o_data_row').first.click()
        step(pg, title, f, '.o_form_view')

    lst('Master Data', 'Estates', 'Master Data: Estates list'); open_first('Estate form')
    lst('Master Data', 'Divisions', 'Master Data: Divisions list'); open_first('Division form')
    lst('Master Data', 'Blocks', 'Master Data: Blocks list'); open_first('Block form (area, stage, boundary)')
    lst('Master Data', 'Landmarks', 'Master Data: Landmarks list'); open_first('Landmark form')
    lst('Operations', 'Field Activities', 'Operations: Field Activities')
    lst('Operations', 'Harvest Tally', 'Operations: Harvest Tally')
    if pg.locator('.o_data_row').count(): open_first('Harvest tally form')
    lst('Operations', 'Transport Notes', 'Operations: Transport Notes')
    lst('Operations', 'Weigh Tickets', 'Operations: Weigh Tickets')
    if pg.locator('.o_data_row').count(): open_first('Weigh ticket form (confirmed, stock link)')
    lst('Mill', 'Extraction Rates', 'Mill: Extraction Rates (OER/KER)')
    lst('Payroll', 'Pay Schemes', 'Payroll: Pay Schemes'); 
    if pg.locator('.o_data_row').count(): open_first('Pay scheme form')
    lst('Payroll', 'Harvest Pay', 'Payroll: Harvest Pay')

    def wiz():
        menu(pg, 'Payroll', 'Compute Harvest Pay'); pg.wait_for_selector('.modal')
    step(pg, 'Payroll: Compute Harvest Pay wizard', wiz, '.modal')
    lst('Reporting', 'Yield and Cost', 'Reporting: Yield and Cost pivot (earlier TypeError)')

    def graph(): pg.locator('button.o_switch_view.o_graph').click()
    step(pg, 'Yield and Cost: graph view', graph, '.o_graph_renderer')
    lst('Configuration', 'Activity Types', 'Config: Activity Types')
    lst('Configuration', 'Landmark Types', 'Config: Landmark Types')
    lst('Configuration', 'Grade Deductions', 'Config: Grade Deductions')
    lst('Configuration', 'FFB Reference Prices', 'Config: FFB Reference Prices')
    def settings():
        menu(pg, 'Configuration', 'Settings'); pg.wait_for_selector('.o_form_view, .o_setting_box, .o_action_manager .o_content', timeout=30000); pg.wait_for_timeout(6000)
    step(pg, 'Config: Settings', settings, '.o_form_view, .o_setting_box, .o_content')

    # create flow: estate + division through the UI
    def new_estate():
        menu(pg, 'Master Data', 'Estates'); pg.locator('.o_list_button_add').click(); settle(pg)
        pg.locator('.o_field_widget[name=name] input').fill('UI Test Estate')
        pg.locator('.o_field_widget[name=code] input').fill('UITEST')
    step(pg, 'Create estate via UI: fill form', new_estate, '.o_form_view')

    def save():
        pg.locator('.o_form_button_save').click()
    def saved():
        save(); pg.wait_for_timeout(1500)
        assert pg.locator('.o_form_button_save:visible').count() == 0, 'form still dirty after save'
    step(pg, 'Create estate via UI: save', saved, '.o_form_view')

    def new_division():
        menu(pg, 'Master Data', 'Divisions'); pg.locator('.o_list_button_add').click(); settle(pg)
        pg.locator('.o_field_widget[name=name] input').fill('UI Test Division')
        pg.locator('.o_field_widget[name=code] input').fill('UI-D1')
        e = pg.locator('.o_field_widget[name=estate_id] input'); e.fill('UI Test'); pg.wait_for_timeout(1200)
        pg.locator('.o_m2o_dropdown_option, .ui-menu-item').first.click(); pg.wait_for_timeout(500)
        pg.locator('.o_form_button_save').click()
    step(pg, 'Create division under new estate via UI', new_division, '.o_form_view')

    def new_block():
        menu(pg, 'Master Data', 'Blocks'); pg.locator('.o_list_button_add').click(); settle(pg)
        pg.locator('.o_field_widget[name=name] input').fill('UI Block 1')
        pg.locator('.o_field_widget[name=code] input').fill('UI-B1')
        pg.locator('.o_field_widget[name=area_ha] input').fill('12.5')
        d = pg.locator('.o_field_widget[name=division_id] input'); d.fill('UI Test'); pg.wait_for_timeout(1200)
        pg.locator('.o_m2o_dropdown_option, .ui-menu-item').first.click(); pg.wait_for_timeout(500)
        pg.locator('.o_form_button_save').click()
    step(pg, 'Create block under new division via UI', new_block, '.o_form_view')

    def set_mature():
        pg.get_by_role('button', name=t('Set Mature')).click(); pg.wait_for_timeout(2500)
        assert pg.locator('.o_statusbar_status .o_arrow_button_current:has-text("%s")' % t('Mature (TM)').split(' ')[0]).count(), 'stage did not move to Mature'
    step(pg, 'Click Set Mature button: block stage becomes Mature (TM)', set_mature, '.o_form_view')

    ctx.close(); b.close()

json.dump(results, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
print('PASS', sum(r['status'] == 'PASS' for r in results), 'FAIL', sum(r['status'] == 'FAIL' for r in results))
