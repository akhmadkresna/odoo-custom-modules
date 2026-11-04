"""Tiny JSON-2 client. Reads KPM_DEV_ODOO_* from the file named by $KPM_CREDENTIALS
(default: ../../../credentials.env, i.e. next to the repository folder)."""
import json, os, urllib.request, urllib.error
CRED = os.environ.get('KPM_CREDENTIALS') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'credentials.env')
env = {}
for line in open(CRED):
    line = line.strip()
    if line.startswith('KPM_DEV_ODOO_') and '=' in line:
        k, v = line.split('=', 1); env[k] = v.strip("'\"")
URL, DB, KEY = env['KPM_DEV_ODOO_URL'], env['KPM_DEV_ODOO_DB'], env['KPM_DEV_ODOO_API_KEY']

class OdooError(Exception): pass

def call(model, method, ids=None, context=None, **kw):
    body = dict(kw)
    if ids is not None: body['ids'] = ids if isinstance(ids, list) else [ids]
    if context: body['context'] = context
    req = urllib.request.Request(f"{URL}/json/2/{model}/{method}", data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': f'bearer {KEY}', 'X-Odoo-Database': DB,
                 'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'KPM-E2E/1.0'})
    try:
        return json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        try: msg = json.loads(e.read().decode()); msg = msg.get('message') or msg
        except Exception: msg = str(e)
        raise OdooError(f"{model}.{method}: {str(msg)[:700]}")

def sr(model, domain=None, fields=None, **kw):
    return call(model, 'search_read', domain=domain or [], fields=fields or ['display_name'], **kw)

def one(model, domain, fields=None):
    r = sr(model, domain, fields, limit=1); return r[0] if r else None
