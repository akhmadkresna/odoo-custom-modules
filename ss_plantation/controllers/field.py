import hashlib
import json
import logging
import os

import psycopg2

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.modules import get_module_path
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

APP_PATH = '/plantation/field'
STATIC_URL = '/ss_plantation/static/field/'
SCHEMA_VERSION = 1

# entry type -> model that stores it, so a replayed entry can be found by its client_uuid
OP_MODELS = {
    'harvest_tally': 'ss.plantation.harvest.tally',
    'transport_note': 'ss.plantation.transport',
    'field_activity': 'ss.plantation.activity',
}

# What the phone caches. model -> (key in the payload, odoo model, fields, domain).
# Rows are read with the device user's own access rights.
MASTER = {
    'divisions': ('ss.plantation.division', ['name', 'code', 'estate_id', 'company_id'], []),
    'blocks': ('ss.plantation.block', [
        'name', 'code', 'division_id', 'stage', 'area_ha', 'avg_bunch_weight_kg'], []),
    'harvesters': ('hr.employee', ['name', 'barcode', 'company_id'], []),  # read with sudo, see _master
    'activity_types': ('ss.plantation.activity.type', ['name', 'code', 'uom_basis', 'requires_inputs'], []),
    'products': ('product.product', ['name', 'default_code', 'uom_id'], [('is_storable', '=', True)]),
    'landmarks': ('ss.plantation.landmark', [
        'name', 'type_id', 'division_id', 'latitude', 'longitude'], []),
}


def _json(data, status=200):
    body = json.dumps(data, default=str)  # ASCII-safe, so Content-Length is right
    return request.make_response(
        body, headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')], status=status)


def _error(code, message, status):
    return _json({'error': code, 'message': message}, status)


def _static_files():
    base = os.path.join(get_module_path('ss_plantation'), 'static', 'field')
    return sorted(
        f for f in os.listdir(base)
        if os.path.isfile(os.path.join(base, f)) and f != 'sw.js')


def _read(name):
    with file_open('ss_plantation/static/field/' + name, 'rb') as f:
        return f.read()


def _assets_version():
    digest = hashlib.sha256()
    for name in _static_files() + ['sw.js']:
        digest.update(name.encode())
        digest.update(_read(name))
    return digest.hexdigest()[:12]


class PlantationFieldApp(http.Controller):

    # ---- the app shell (public, so it also loads for a signed-out phone) ----

    @http.route(APP_PATH, type='http', auth='public', methods=['GET'], readonly=True)
    def shell(self, **kw):
        return request.make_response(_read('index.html'), headers=[
            ('Content-Type', 'text/html; charset=utf-8'), ('Cache-Control', 'no-cache')])

    @http.route(APP_PATH + '/manifest.json', type='http', auth='public', methods=['GET'], readonly=True)
    def manifest(self, **kw):
        return request.make_response(json.dumps({
            'name': 'Plantation Field', 'short_name': 'Field',
            'start_url': APP_PATH, 'scope': APP_PATH, 'display': 'standalone',
            'background_color': '#ffffff', 'theme_color': '#1f6b3a',
            'icons': [
                {'src': '/ss_plantation/static/description/icon.png', 'sizes': '128x128', 'type': 'image/png'},
            ],
        }), headers=[('Content-Type', 'application/manifest+json'), ('Cache-Control', 'no-cache')])

    @http.route(APP_PATH + '/sw.js', type='http', auth='public', methods=['GET'], readonly=True)
    def service_worker(self, **kw):
        assets = [APP_PATH, APP_PATH + '/manifest.json', '/ss_plantation/static/description/icon.png']
        assets += [STATIC_URL + name for name in _static_files()]
        script = _read('sw.js').decode()
        script = script.replace('__VERSION__', _assets_version()).replace(
            '__ASSETS__', json.dumps(assets))
        return request.make_response(script, headers=[
            ('Content-Type', 'application/javascript; charset=utf-8'),
            ('Service-Worker-Allowed', APP_PATH),
            ('Cache-Control', 'no-cache')])

    # ---- pairing: runs with a normal Odoo login, so passwords and 2FA work as usual ----

    @http.route(APP_PATH + '/api/register', type='http', auth='user', methods=['POST'], csrf=False)
    def register(self, **kw):
        # Demanding JSON makes a cross-site form post impossible without a CORS preflight.
        if 'application/json' not in (request.httprequest.content_type or ''):
            return _error('bad_request', "Expected JSON.", 400)
        user = request.env.user
        if not user.has_group('ss_plantation.group_plantation_user'):
            return _error('forbidden', "This account has no plantation access.", 403)
        try:
            data = request.get_json_data()
        except ValueError:
            return _error('bad_request', "Invalid JSON.", 400)
        name = (data.get('device_name') or '').strip()[:64]
        device, token = request.env['ss.plantation.field.device']._issue(user, name)
        return _json({
            'token': token, 'device_id': device.id,
            'user': {'id': user.id, 'name': user.name},
            'server_time': str(fields.Datetime.now()),
            'schema_version': SCHEMA_VERSION,
        })

    # ---- token-authenticated API ----

    def _device(self):
        header = request.httprequest.headers.get('Authorization', '')
        token = header[7:].strip() if header[:7].lower() == 'bearer ' else ''
        device = request.env['ss.plantation.field.device']._authenticate(token)
        if not device:
            return None
        user = device.user_id
        if not user.has_group('ss_plantation.group_plantation_user'):
            return None
        request.update_env(user=user.id, context={
            **request.env.context, 'allowed_company_ids': user.company_ids.ids})
        return device

    def _master(self, since=None):
        """All master data (since=None) or what changed since `since`. `ids` always lists
        every visible id, so the phone can drop rows that were deleted or made invisible."""
        out, ids = {}, {}
        for key, (model, field_names, domain) in MASTER.items():
            env_model = request.env[model]
            if model == 'hr.employee':
                # Names and badges of employees in the user's companies are all a tally clerk
                # needs; the rest of the employee record stays HR-only.
                env_model = env_model.sudo()
                domain = domain + [('company_id', 'in', request.env.user.company_ids.ids)]
            ids[key] = env_model.search(list(domain)).ids
            if since:
                rows = env_model.with_context(active_test=False).search(
                    domain + [('write_date', '>=', since)])
            else:
                rows = env_model.search(domain)
            out[key] = [self._row(r, field_names) for r in rows]
        return out, ids

    @staticmethod
    def _row(record, field_names):
        row = {'id': record.id}
        if record._name == 'product.product':
            row['uom_name'] = record.uom_id.name or ''
        if 'active' in record._fields:
            row['active'] = record.active
        for fname in field_names:
            value = record[fname]
            field = record._fields[fname]
            if field.type == 'many2one':
                row[fname] = value.id or False
            elif field.type in ('float', 'integer', 'boolean'):
                row[fname] = value
            else:
                row[fname] = value or ''
        return row

    @http.route(APP_PATH + '/api/ping', type='http', auth='public', methods=['GET'], csrf=False)
    def ping(self, **kw):
        device = self._device()
        if not device:
            return _error('unauthorized', "Device not recognised.", 401)
        return _json({'ok': True, 'server_time': str(fields.Datetime.now()), 'user': request.env.user.name})

    @http.route(APP_PATH + '/api/bootstrap', type='http', auth='public', methods=['GET'], csrf=False)
    def bootstrap(self, **kw):
        device = self._device()
        if not device:
            return _error('unauthorized', "Device not recognised.", 401)
        server_time = str(fields.Datetime.now())  # taken first, so nothing changing meanwhile is missed
        data, ids = self._master()
        return _json({
            'server_time': server_time, 'schema_version': SCHEMA_VERSION,
            'user': {'id': request.env.user.id, 'name': request.env.user.name},
            'data': data, 'ids': ids,
        })

    @http.route(APP_PATH + '/api/delta', type='http', auth='public', methods=['GET'], csrf=False)
    def delta(self, since=None, **kw):
        device = self._device()
        if not device:
            return _error('unauthorized', "Device not recognised.", 401)
        if not since:
            return _error('bad_request', "Missing 'since'.", 400)
        server_time = str(fields.Datetime.now())
        data, ids = self._master(since=since)
        return _json({
            'server_time': server_time, 'schema_version': SCHEMA_VERSION, 'data': data, 'ids': ids})

    # ---- sync: apply the phone's queued entries, one result per entry ----

    @http.route(APP_PATH + '/api/sync', type='http', auth='public', methods=['POST'], csrf=False)
    def sync(self, **kw):
        device = self._device()
        if not device:
            return _error('unauthorized', "Device not recognised.", 401)
        try:
            ops = request.get_json_data().get('ops') or []
        except (ValueError, AttributeError):
            return _error('bad_request', "Invalid JSON.", 400)
        if not isinstance(ops, list) or len(ops) > 200:
            return _error('bad_request', "Send at most 200 entries per call.", 400)
        results = [self._apply(op, device) for op in ops]
        device._touch()
        return _json({'results': results, 'server_time': str(fields.Datetime.now())})

    def _apply(self, op, device):
        uuid = op.get('uuid') if isinstance(op, dict) else None
        if not uuid or not isinstance(uuid, str) or len(uuid) > 64:
            return {'uuid': uuid, 'status': 'rejected', 'code': 'bad_request',
                    'message': request.env._("Entry has no valid id.")}
        handler = getattr(self, '_op_' + str(op.get('type')), None)
        if handler is None:
            return {'uuid': uuid, 'status': 'rejected', 'code': 'unknown_type',
                    'message': request.env._("Unknown entry type.")}
        try:
            with request.env.cr.savepoint():
                record, created = handler(uuid, op.get('payload') or {}, device)
        except AccessError as e:
            return {'uuid': uuid, 'status': 'rejected', 'code': 'access', 'message': str(e)}
        except (ValidationError, UserError) as e:
            return {'uuid': uuid, 'status': 'rejected', 'code': 'validation', 'message': str(e)}
        except (ValueError, TypeError, AttributeError):
            return {'uuid': uuid, 'status': 'rejected', 'code': 'bad_request',
                    'message': request.env._("The entry has an invalid value.")}
        except psycopg2.IntegrityError:
            # Another request stored the same entry first, or a database rule refused it.
            existing = request.env[OP_MODELS.get(op.get('type'), 'ss.plantation.harvest.tally')].search(
                [('client_uuid', '=', uuid)], limit=1)
            if existing:
                return {'uuid': uuid, 'status': 'duplicate', 'id': existing.id, 'name': existing.name}
            return {'uuid': uuid, 'status': 'rejected', 'code': 'validation',
                    'message': request.env._("The entry breaks a data rule (for example a negative count).")}
        except Exception:  # an unexpected failure must not lose or block the other entries
            _logger.exception("Field sync failed for %s", uuid)
            return {'uuid': uuid, 'status': 'error', 'code': 'server',
                    'message': request.env._("Server error. It will be retried.")}
        return {'uuid': uuid, 'status': 'ok' if created else 'duplicate',
                'id': record.id, 'name': record.name}

    def _op_harvest_tally(self, uuid, p, device):
        env = request.env
        Tally = env['ss.plantation.harvest.tally']
        division = env['ss.plantation.division'].browse(int(p.get('division_id') or 0)).exists()
        if not division:
            raise ValidationError(env._("The division no longer exists."))
        existing = Tally.search([('client_uuid', '=', uuid), ('company_id', '=', division.company_id.id)], limit=1)
        if existing:
            return existing, False
        lines = []
        for line in p.get('lines') or []:
            lines.append((0, 0, {
                'block_id': int(line.get('block_id') or 0),
                'harvester_id': int(line.get('harvester_id') or 0),
                'bunches_ripe': int(line.get('bunches_ripe') or 0),
                'bunches_unripe': int(line.get('bunches_unripe') or 0),
                'bunches_overripe': int(line.get('bunches_overripe') or 0),
                'loose_fruit_kg': float(line.get('loose_fruit_kg') or 0),
            }))
        if not lines:
            raise ValidationError(env._("The tally has no lines."))
        for _op, _i, vals in lines:
            if min(vals['bunches_ripe'], vals['bunches_unripe'], vals['bunches_overripe'],
                   vals['loose_fruit_kg']) < 0:
                raise ValidationError(env._("Bunch counts and loose fruit weight cannot be negative."))
        tally = Tally.create({
            'date': p.get('date') or fields.Date.context_today(Tally),
            'division_id': division.id,
            'company_id': division.company_id.id,
            'client_uuid': uuid,
            'field_device_id': device.id,
            'clerk_id': env.user.employee_ids.filtered(
                lambda e: e.company_id == division.company_id)[:1].id or False,
            'line_ids': lines,
        })
        return tally, True

    def _employee(self, value, company):
        """An employee id from the phone, or an empty record when none was given."""
        if not value:
            return request.env['hr.employee']
        employee = request.env['hr.employee'].sudo().browse(int(value)).exists()
        if not employee or employee.company_id != company:
            raise ValidationError(request.env._("An employee is not in the company of this entry."))
        return employee

    def _op_transport_note(self, uuid, p, device):
        env = request.env
        Note = env['ss.plantation.transport']
        division = env['ss.plantation.division'].browse(int(p.get('division_id') or 0)).exists()
        if not division:
            raise ValidationError(env._("The division no longer exists."))
        existing = Note.search([('client_uuid', '=', uuid), ('company_id', '=', division.company_id.id)], limit=1)
        if existing:
            return existing, False
        lines = []
        for line in p.get('lines') or []:
            block = env['ss.plantation.block'].browse(int(line.get('block_id') or 0)).exists()
            if not block:
                raise ValidationError(env._("A block no longer exists."))
            if block.division_id != division:
                raise ValidationError(env._(
                    "Block %(block)s is not in division %(division)s.",
                    block=block.display_name, division=division.display_name))
            bunches = int(line.get('bunches') or 0)
            if bunches <= 0:
                raise ValidationError(env._("Bunches must be positive."))
            lines.append((0, 0, {'block_id': block.id, 'bunches': bunches}))
        if not lines:
            raise ValidationError(env._("The transport note has no lines."))
        vals = {
            'date': p.get('date') or fields.Date.context_today(Note),
            'division_id': division.id,
            'company_id': division.company_id.id,
            'plate': str(p.get('plate') or '').strip().upper()[:32],
            'driver_id': self._employee(p.get('driver_id'), division.company_id).id or False,
            'client_uuid': uuid,
            'field_device_id': device.id,
            'line_ids': lines,
        }
        if p.get('harvested_at'):
            vals['harvested_at'] = fields.Datetime.to_datetime(p['harvested_at'])
        return Note.create(vals), True

    def _op_field_activity(self, uuid, p, device):
        env = request.env
        Activity = env['ss.plantation.activity']
        block = env['ss.plantation.block'].browse(int(p.get('block_id') or 0)).exists()
        if not block:
            raise ValidationError(env._("The block no longer exists."))
        existing = Activity.search([('client_uuid', '=', uuid), ('company_id', '=', block.company_id.id)], limit=1)
        if existing:
            return existing, False
        act_type = env['ss.plantation.activity.type'].browse(int(p.get('type_id') or 0)).exists()
        if not act_type:
            raise ValidationError(env._("The activity type no longer exists."))
        quantity = float(p.get('quantity') or 0)
        man_days = float(p.get('man_days') or 0)
        if quantity < 0 or man_days < 0:
            raise ValidationError(env._("Quantity and man days cannot be negative."))
        if not quantity and act_type.uom_basis == 'ha':
            quantity = block.area_ha
        inputs = []
        for line in p.get('inputs') or []:
            product = env['product.product'].browse(int(line.get('product_id') or 0)).exists()
            qty = float(line.get('qty') or 0)
            if not product:
                raise ValidationError(env._("A product no longer exists."))
            if qty <= 0:
                raise ValidationError(env._("The input quantity must be positive."))
            inputs.append((0, 0, {'product_id': product.id, 'qty': qty}))
        workers = [self._employee(w, block.company_id).id for w in (p.get('employee_ids') or [])]
        activity = Activity.create({
            'date': p.get('date') or fields.Date.context_today(Activity),
            'block_id': block.id,
            'company_id': block.company_id.id,
            'type_id': act_type.id,
            'quantity': quantity,
            'man_days': man_days,
            'note': str(p.get('note') or '')[:2000],
            'input_line_ids': inputs,
            'client_uuid': uuid,
            'field_device_id': device.id,
        })
        if workers:
            # Clerks may not touch employee records, yet recording who worked is their job.
            activity.sudo().employee_ids = [(6, 0, workers)]
        return activity, True
