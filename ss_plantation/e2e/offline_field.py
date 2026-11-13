"""Browser test for the offline field app: pair, go offline, record, come back online, sync.

    APP_HOST=... ODOO_LOGIN=... ODOO_PW=... ODOO_DB=... ODOO_API_KEY=... python3 offline_field.py [out_dir]

Env (all required unless noted): APP_HOST is the HTTPS host of the field app; ODOO_LOGIN / ODOO_PW
sign in once to pair; ODOO_DB; API_URL is the Odoo URL used for checks and clean-up; ODOO_API_KEY
(JSON-2, rpc scope) is only used to check results and delete what the run created. Optional:
APP_IP maps APP_HOST to that address, for use before public DNS catches up.
"""
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HOST = os.environ['APP_HOST']
IP = os.environ.get('APP_IP')
DB = os.environ['ODOO_DB']
LOGIN = os.environ['ODOO_LOGIN']
PW = os.environ['ODOO_PW']
KEY = os.environ['ODOO_API_KEY']
API = os.environ['API_URL']
# Names of the test records. Change them to something realistic when capturing screenshots for a guide.
HARVESTER = os.environ.get('E2E_HARVESTER', 'E2E Harvester')
PRODUCT = os.environ.get('E2E_PRODUCT', 'E2E NPK')
ACT_TYPE = os.environ.get('E2E_ACT_TYPE', 'E2E Fertilising')
NOTE = os.environ.get('E2E_NOTE', 'Round 2')
DIVISION = os.environ.get('E2E_DIVISION')  # name of the division to record in; first one when not set
COMPANY = int(os.environ['E2E_COMPANY']) if os.environ.get('E2E_COMPANY') else None  # company of the people created
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else 'offline_out')
OUT.mkdir(parents=True, exist_ok=True)
results = []
CREATED = {}  # records this run made, by model: only these are removed at the end


def rpc(model, method, **kw):
    req = urllib.request.Request(
        f'{API}/json/2/{model}/{method}', data=json.dumps(kw).encode(),
        headers={'Authorization': 'bearer ' + KEY, 'X-Odoo-Database': DB, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)


def wait_for(page, expr, timeout=20000):
    """Poll `expr` until truthy. It may be a promise: the value is awaited each time."""
    deadline = time.time() + timeout / 1000
    while True:
        if page.evaluate(f'async () => !!(await ({expr}))'):
            return
        if time.time() > deadline:
            raise TimeoutError('timed out waiting for: ' + expr)
        time.sleep(0.3)


def shot(page, name):
    page.screenshot(path=str(OUT / f'{name}.png'))


def outbox(page):
    return page.evaluate('window.__field.db.all("outbox")')


def add_line(page, harvester, block_text, ripe):
    page.fill('#d-hq', harvester[:4])
    page.click(f'#d-results button:has-text("{harvester}")')
    page.select_option('#d-block', label=block_text)
    page.fill('#d-ripe', str(ripe))
    page.click('button[data-action="add-line"]')


def cleanup(uuids=()):
    ids = rpc('ss.plantation.harvest.tally', 'search', domain=[
        '|', ['client_uuid', 'in', list(uuids)], ['field_device_id.name', '=', 'E2E phone']],
        context={'active_test': False})
    if ids:
        rpc('ss.plantation.harvest.tally', 'unlink', ids=ids)
    for model in ('ss.plantation.transport', 'ss.plantation.activity'):
        ids = rpc(model, 'search', domain=[['field_device_id.name', '=', 'E2E phone']], context={'active_test': False})
        if ids:
            rpc(model, 'unlink', ids=ids)
    for model, rec_id in CREATED.items():
        if rec_id:
            rpc(model, 'unlink', ids=[rec_id])
    if HARVESTER.startswith('E2E'):  # leftovers of an interrupted run, found by their test names
        recent = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
        for model, name in (('product.product', PRODUCT), ('ss.plantation.activity.type', ACT_TYPE), ('hr.employee', HARVESTER)):
            ids = rpc(model, 'search', domain=[['name', '=', name], ['create_date', '>=', recent]], context={'active_test': False})
            if ids:
                rpc(model, 'unlink', ids=ids)
    dev = rpc('ss.plantation.field.device', 'search', domain=[['name', '=', 'E2E phone']], context={'active_test': False})
    if dev:
        rpc('ss.plantation.field.device', 'unlink', ids=dev)


def main():
    created_uuids = []
    cleanup()  # leftovers from an interrupted run
    try:
        run(created_uuids)
    finally:
        cleanup(created_uuids)
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} checks passed; screenshots in {OUT}')
    sys.exit(1 if failed else 0)


def run(created_uuids):
    employee = rpc('hr.employee', 'create', vals_list=[{'name': HARVESTER, **({'company_id': COMPANY} if COMPANY else {})}])[0]
    CREATED['hr.employee'] = employee
    # reuse a product / activity type of that name when it exists; only what this run creates is removed afterwards
    found = rpc('product.product', 'search', domain=[['name', '=', PRODUCT], ['is_storable', '=', True]])
    npk = found[0] if found else rpc('product.product', 'create', vals_list=[{'name': PRODUCT, 'type': 'consu', 'is_storable': True}])[0]
    CREATED['product.product'] = None if found else npk
    found = rpc('ss.plantation.activity.type', 'search', domain=[['name', '=', ACT_TYPE], ['requires_inputs', '=', True]])
    act_type = found[0] if found else rpc('ss.plantation.activity.type', 'create', vals_list=[{'name': ACT_TYPE, 'uom_basis': 'ha', 'requires_inputs': True}])[0]
    CREATED['ss.plantation.activity.type'] = None if found else act_type
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[f'--host-resolver-rules=MAP {HOST} {IP}'] if IP else [])
        ctx = browser.new_context(viewport={'width': 390, 'height': 780}, locale='id-ID')
        page = ctx.new_page()
        page.on('pageerror', lambda e: print('PAGEERROR', e))
        page.add_init_script(f'window.__e2e_name = {json.dumps(HARVESTER)}; window.__e2e_div = {json.dumps(DIVISION)};')
        base = f'https://{HOST}'

        # 1. sign in once with the normal Odoo login, then pair
        page.goto(f'{base}/web/login?db={DB}')
        page.fill('input[name=login]', LOGIN)
        page.fill('input[name=password]', PW)
        page.click('button[type=submit]')
        page.wait_for_url('**/odoo**', timeout=30000)
        page.goto(f'{base}/plantation/field')
        wait_for(page, '!!document.querySelector("[data-action=pair]")')
        shot(page, '01_pair')
        page.fill('#devname', 'E2E phone')
        page.click('[data-action=pair]')
        wait_for(page, 'document.querySelector("[data-action=tally]")', 60000)
        check('pairing works and lands on home', True)
        wait_for(page, 'window.__field.db.getMeta("master_time").then(v => !!v)')
        cache = page.evaluate('Promise.all(["divisions","blocks","harvesters"].map(k => window.__field.sync.master(k).then(r => r.length)))')
        check('reference data cached', all(n > 0 for n in cache), str(cache))
        shot(page, '02_home')

        # 2. service worker controls the page, then the shell loads with no network
        page.evaluate('navigator.serviceWorker.ready')
        page.reload()
        wait_for(page, '!!navigator.serviceWorker.controller')
        check('service worker controls the page', True)
        ctx.set_offline(True)
        page.reload()
        wait_for(page, 'document.querySelector("[data-action=tally]")')
        check('app shell loads while offline', True)
        check('offline state is shown', page.inner_text('header .pill') in ('Offline',))
        shot(page, '03_offline_home')

        # 3. record a tally with no network
        page.click('[data-action=tally]')
        page.click('[data-action=new-tally]')
        info = page.evaluate('''async () => {
            const s = window.__field.sync;
            const d = (await s.master("divisions")).find(x => !window.__e2e_div || x.name === window.__e2e_div);
            const blocks = (await s.master("blocks")).filter(b => b.division_id === d.id && b.stage === "mature");
            const h = (await s.master("harvesters")).find(x => x.name === window.__e2e_name);
            return {division: d.id, block: blocks[0] && (blocks[0].code + " - " + blocks[0].name), harvester: h.name};
        }''')
        page.select_option('#f-division', value=str(info['division']))
        add_line(page, info['harvester'], info['block'], 12)
        shot(page, '04_form_line_added')
        page.click('[data-action=save-tally]')
        wait_for(page, 'window.__field.db.all("outbox").then(r => r.length === 1)')
        rows = outbox(page)
        check('entry saved to the local outbox offline', rows[0]['status'] == 'pending')
        created_uuids.append(rows[0]['uuid'])
        shot(page, '05_pending_list')

        # 4. a duplicate for the same worker/block/day is refused locally, before any signal
        page.click('[data-action=new-tally]')
        page.select_option('#f-division', value=str(info['division']))
        add_line(page, info['harvester'], info['block'], 3)
        shot(page, '05b_duplicate')
        check('duplicate worker/block/day blocked on the phone', 'sudah dicatat' in page.inner_text('main'), page.inner_text('main')[-200:].replace('\n', ' | '))
        page.click('[data-action=tally]')

        # 5. back online: sync sends it exactly once
        ctx.set_offline(False)
        page.evaluate('window.dispatchEvent(new Event("online"))')
        try:
            wait_for(page, 'window.__field.db.all("outbox").then(r => r.length === 1 && r[0].status === "synced")', 30000)
        except TimeoutError:
            print('DEBUG outbox', json.dumps(outbox(page))[:600])
            print('DEBUG state', page.evaluate('JSON.stringify(window.__field.sync.state)'))
            shot(page, 'debug_sync')
            raise
        rec = rpc('ss.plantation.harvest.tally', 'search_read',
                  domain=[['client_uuid', '=', created_uuids[0]]], fields=['name', 'state', 'bunch_total', 'field_device_id'])
        check('entry reached Odoo as one draft', len(rec) == 1 and rec[0]['state'] == 'draft', str(rec))
        check('Odoo shows the device it came from', rec and rec[0]['field_device_id'] and 'E2E phone' in rec[0]['field_device_id'][1])
        shot(page, '06_synced')

        # 6. replaying the same entry creates no second record
        page.evaluate('''async () => { const db = window.__field.db; const r = (await db.all("outbox"))[0];
            r.status = "pending"; r.next_try = 0; await db.put("outbox", r); }''')
        page.click('button.sync')
        wait_for(page, 'window.__field.db.all("outbox").then(r => r[0].status === "synced")')
        count = rpc('ss.plantation.harvest.tally', 'search_count', domain=[['client_uuid', '=', created_uuids[0]]])
        check('re-sending the same entry does not duplicate it', count == 1, str(count))

        # 6b. transport note and field activity recorded offline, sent later
        ctx.set_offline(True)
        page.evaluate('window.dispatchEvent(new Event("offline"))')
        page.click('[data-action=home]')
        page.click('[data-action=transport]')
        page.click('[data-action=new-transport]')
        page.select_option('#tf-division', value=str(info['division']))
        page.fill('#tf-plate', 'kt 1234 ab')
        page.fill('#pk-driver', HARVESTER[:4])
        page.click('#pk-driver-results button')
        page.select_option('#tf-block', label=info['block'])
        page.fill('#tf-bunches', '40')
        page.click('[data-action=add-tline]')
        shot(page, '06b_transport_form')
        page.click('[data-action=save-transport]')
        wait_for(page, 'window.__field.db.all("outbox").then(r => r.some(e => e.type === "transport_note" && e.status === "pending"))')
        check('transport note saved on the phone while offline', True)

        page.click('[data-action=home]')
        page.click('[data-action=activity]')
        page.click('[data-action=new-activity]')
        block_id = page.evaluate('async (d) => (await window.__field.sync.master("blocks")).find(b => b.division_id === d && b.stage === "mature").id', info['division'])
        page.select_option('#af-block', value=str(block_id))
        page.select_option('#af-type', value=str(act_type))
        check('activity quantity defaults to the block area', page.input_value('#af-quantity') not in ('', '0'), page.input_value('#af-quantity'))
        page.fill('#af-man_days', '4')
        page.fill('#pk-worker', HARVESTER[:4])
        page.click('#pk-worker-results button')
        page.fill('#pk-product', PRODUCT[:6])
        page.click('#pk-product-results button')
        page.fill('#af-inqty', '5')
        page.click('[data-action=add-input]')
        page.fill('#af-note', NOTE)
        page.evaluate('window.scrollTo(0, 0)')
        shot(page, '06c_activity_form')
        page.click('[data-action=save-activity]')
        wait_for(page, 'window.__field.db.all("outbox").then(r => r.some(e => e.type === "field_activity" && e.status === "pending"))')
        check('field activity saved on the phone while offline', True)

        ctx.set_offline(False)
        page.evaluate('window.dispatchEvent(new Event("online"))')
        wait_for(page, 'window.__field.db.all("outbox").then(r => r.filter(e => e.type !== "harvest_tally").every(e => e.status === "synced") && r.some(e => e.type === "transport_note"))', 40000)
        notes = rpc('ss.plantation.transport', 'search_read', domain=[['field_device_id.name', '=', 'E2E phone']],
                    fields=['state', 'plate', 'bunch_total', 'driver_id', 'harvested_at'])
        check('transport note reached Odoo as a draft with plate, driver and bunches',
              len(notes) == 1 and notes[0]['state'] == 'draft' and notes[0]['plate'] == 'KT 1234 AB' and notes[0]['bunch_total'] == 40
              and notes[0]['driver_id'], str(notes))
        acts = rpc('ss.plantation.activity', 'search_read', domain=[['field_device_id.name', '=', 'E2E phone']],
                   fields=['state', 'man_days', 'employee_ids', 'input_line_ids', 'note', 'quantity'])
        check('field activity reached Odoo as a draft with worker, input and note',
              len(acts) == 1 and acts[0]['state'] == 'draft' and acts[0]['man_days'] == 4 and len(acts[0]['employee_ids']) == 1
              and len(acts[0]['input_line_ids']) == 1 and acts[0]['note'] == NOTE and acts[0]['quantity'] > 0, str(acts))
        shot(page, '06d_all_synced')

        # 7. a server-side rejection lands in Needs attention with a readable reason
        ctx.set_offline(True)
        page.evaluate('window.dispatchEvent(new Event("offline"))')
        entry = page.evaluate('''async (info) => { const s = window.__field.sync;
            const blocks = (await s.master("blocks")).filter(b => b.division_id === info.division && b.stage === "mature");
            const h = (await s.master("harvesters")).find(x => x.name === window.__e2e_name);
            const e = await s.enqueue("harvest_tally", {date: new Date(Date.now() + 864e5).toLocaleDateString("sv"),
              division_id: info.division, lines: [{harvester_id: h.id, harvester_name: h.name, block_id: blocks[0].id,
              block_name: blocks[0].code, bunches_ripe: 5, bunches_overripe: 0, bunches_unripe: 0, loose_fruit_kg: 0},
              {harvester_id: h.id, harvester_name: h.name, block_id: blocks[0].id,
              block_name: blocks[0].code, bunches_ripe: 2, bunches_overripe: 0, bunches_unripe: 0, loose_fruit_kg: 0}]});
            return e.uuid; }''', info)
        created_uuids.append(entry)
        ctx.set_offline(False)
        page.evaluate('window.dispatchEvent(new Event("online"))')
        wait_for(page, f'window.__field.db.get("outbox", "{entry}").then(r => r.status === "rejected")', 30000)
        page.click('[data-action=home]')
        page.click('[data-action=attention]')
        wait_for(page, 'document.querySelector("main li .error")')
        txt = page.inner_text('main li .error')
        check('rejected entry is listed under Needs attention with a reason', HARVESTER in txt and len(txt) > 20, txt)
        shot(page, '07_attention')

        # 8. reference-data delta: archive a block on the server, the phone drops it
        before = page.evaluate('window.__field.sync.master("blocks").then(r => r.length)')
        bid = rpc('ss.plantation.block', 'search', domain=[['stage', '=', 'mature']], limit=1, order='id desc')[0]
        rpc('ss.plantation.block', 'write', ids=[bid], vals={'active': False})
        try:
            page.evaluate('window.__field.sync.refreshMaster()')
            after = page.evaluate('window.__field.sync.master("blocks").then(r => r.length)')
            check('archived block disappears from the phone after a refresh', after == before - 1, f'{before}->{after}')
        finally:
            rpc('ss.plantation.block', 'write', ids=[bid], vals={'active': True})
        browser.close()



if __name__ == '__main__':
    main()
