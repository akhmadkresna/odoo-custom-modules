"""Delete the estate, division and block that ui_plantation.py creates by hand (UITEST / UI-D1 / UI-B1),
so the next run starts clean. Env: API_URL, ODOO_DB, ODOO_API_KEY, E2E_COMPANY."""
import json, os, urllib.request

URL, DB, KEY = os.environ['API_URL'], os.environ['ODOO_DB'], os.environ['ODOO_API_KEY']
CTX = {'allowed_company_ids': sorted({1, int(os.environ.get('E2E_COMPANY', 1))}), 'active_test': False}


def rpc(model, method, **kw):
    req = urllib.request.Request(f'{URL}/json/2/{model}/{method}', data=json.dumps({**kw, 'context': CTX}).encode(),
                                 headers={'Authorization': 'bearer ' + KEY, 'X-Odoo-Database': DB, 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=60))


for model, code in (('ss.plantation.block', 'UI-B1'), ('ss.plantation.division', 'UI-D1'), ('ss.plantation.estate', 'UITEST')):
    ids = rpc(model, 'search', domain=[['code', '=', code]])
    if ids:
        rpc(model, 'unlink', ids=ids)
        print('deleted', model, ids)
