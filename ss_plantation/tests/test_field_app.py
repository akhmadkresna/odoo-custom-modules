import json
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

from .common import SsPlantationCommon

API = '/plantation/field/api/'


@tagged('post_install', '-at_install')
class TestFieldApp(SsPlantationCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = cls.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Field Clerk', 'login': 'field_clerk', 'password': 'field_clerk',
            'group_ids': [Command.set([cls.env.ref('ss_plantation.group_plantation_user').id])],
        })
        cls.device, cls.token = cls.env['ss.plantation.field.device']._issue(cls.clerk, 'Test phone')

    def _get(self, path, token=None):
        headers = {'Authorization': 'Bearer ' + (self.token if token is None else token)}
        return self.url_open(API + path, headers=headers)

    def _post(self, path, payload, token=None):
        headers = {'Authorization': 'Bearer ' + (self.token if token is None else token),
                   'Content-Type': 'application/json'}
        return self.url_open(API + path, data=json.dumps(payload), headers=headers)

    def _tally_op(self, uuid, harvester=None, block=None, **extra):
        return {'uuid': uuid, 'type': 'harvest_tally', 'payload': {
            'date': str(fields.Date.today()), 'division_id': self.division.id,
            'lines': [{
                'block_id': (block or self.block).id,
                'harvester_id': (harvester or self.harvester).id,
                'bunches_ripe': 10, **extra}],
        }}

    # ---- pairing and tokens ----

    def test_register_needs_login_and_json(self):
        res = self.url_open(API + 'register', data=json.dumps({'device_name': 'x'}),
                            headers={'Content-Type': 'application/json'})
        self.assertIn('/web/login', res.url, "signed out: sent to the login page, no token issued")
        self.assertNotIn('"device_id"', res.text)
        self.authenticate('field_clerk', 'field_clerk')
        res = self.url_open(API + 'register', data={'device_name': 'x'})  # not JSON
        self.assertEqual(res.status_code, 400)
        res = self.url_open(API + 'register', data=json.dumps({'device_name': 'My phone'}),
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 200)
        token = res.json()['token']
        device = self.env['ss.plantation.field.device']._authenticate(token)
        self.assertEqual(device.user_id, self.clerk)
        self.assertEqual(device.name, 'My phone')
        self.assertNotEqual(device.token_hash, token, "the token must be stored hashed")

    def test_register_refused_without_plantation_group(self):
        self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Other', 'login': 'other_user', 'password': 'other_user',
            'group_ids': [Command.set([self.env.ref('base.group_user').id])],
        })
        self.authenticate('other_user', 'other_user')
        res = self.url_open(API + 'register', data=json.dumps({}),
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 403)

    def test_bad_revoked_and_expired_tokens(self):
        self.assertEqual(self._get('ping', token='nonsense').status_code, 401)
        self.assertEqual(self._get('ping', token='').status_code, 401)
        self.assertEqual(self._get('ping').status_code, 200)
        self.device.expires_at = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(self._get('ping').status_code, 401)
        self.device.expires_at = fields.Datetime.now() + timedelta(days=5)
        self.device.active = False
        self.assertEqual(self._get('ping').status_code, 401)
        self.device.active = True

    def test_sync_slides_expiry(self):
        soon = fields.Datetime.now() + timedelta(days=1)
        self.device.expires_at = soon
        self.assertEqual(self._post('sync', {'ops': []}).status_code, 200)
        self.assertGreater(self.device.expires_at, soon + timedelta(days=30))
        self.assertTrue(self.device.last_sync)

    # ---- reference data ----

    def test_bootstrap_contents_and_delta(self):
        data = self._get('bootstrap').json()
        self.assertIn(self.block.id, [b['id'] for b in data['data']['blocks']])
        self.assertIn(self.division.id, [d['id'] for d in data['data']['divisions']])
        self.assertIn(self.harvester.id, [h['id'] for h in data['data']['harvesters']])
        block_row = next(b for b in data['data']['blocks'] if b['id'] == self.block.id)
        self.assertEqual(block_row['division_id'], self.division.id)
        self.assertEqual(block_row['stage'], 'mature')

        since = str(fields.Datetime.now())
        delta = self._get('delta?since=' + since).json()
        self.assertEqual(delta['data']['blocks'], [], "nothing changed since the snapshot")
        self.assertIn(self.block.id, delta['ids']['blocks'])

        self.block_b.write({'name': 'Renamed block'})
        self.block.active = False
        self.env.flush_all()
        # Tests run in one transaction, so stamps are the test's start time. Move the two
        # edits after the snapshot, as they would be for a real change made later.
        self.env.cr.execute(
            "UPDATE ss_plantation_block SET write_date = write_date + interval '1 day' WHERE id IN %s",
            [(self.block.id, self.block_b.id)])
        self.env.invalidate_all()
        delta = self._get('delta?since=' + since).json()
        changed = {b['id']: b for b in delta['data']['blocks']}
        self.assertEqual(changed[self.block_b.id]['name'], 'Renamed block')
        self.assertIs(changed[self.block.id]['active'], False)
        self.assertNotIn(self.block.id, delta['ids']['blocks'], "archived rows leave the id list")
        self.assertEqual(self._get('delta').status_code, 400)

    # ---- sync ----

    def test_sync_creates_tally_and_replay_is_harmless(self):
        op = self._tally_op('11111111-1111-4111-8111-111111111111')
        res = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual(res['status'], 'ok')
        tally = self.env['ss.plantation.harvest.tally'].browse(res['id'])
        self.assertEqual(tally.client_uuid, op['uuid'])
        self.assertEqual(tally.state, 'draft', "the app only ever creates drafts")
        self.assertEqual(tally.field_device_id, self.device)
        self.assertEqual(tally.line_ids.bunches_ripe, 10)
        self.assertEqual(tally.create_uid, self.clerk)

        again = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual(again['status'], 'duplicate')
        self.assertEqual(again['id'], tally.id)
        self.assertEqual(self.env['ss.plantation.harvest.tally'].search_count(
            [('client_uuid', '=', op['uuid'])]), 1)

    def test_rejected_entry_does_not_block_others_or_leave_partial_data(self):
        immature = self._make_block('TIM1', 18.0, stage='immature')
        bad = self._tally_op('22222222-2222-4222-8222-222222222222', block=immature)
        good = self._tally_op('33333333-3333-4333-8333-333333333333', harvester=self.harvester_2)
        results = self._post('sync', {'ops': [bad, good]}).json()['results']
        self.assertEqual([r['status'] for r in results], ['rejected', 'ok'])
        self.assertEqual(results[0]['code'], 'validation')
        self.assertTrue(results[0]['message'])
        self.assertFalse(self.env['ss.plantation.harvest.tally'].search(
            [('client_uuid', '=', bad['uuid'])]), "a rejected entry leaves nothing behind")

    def test_duplicate_harvester_block_day_is_rejected(self):
        first = self._tally_op('44444444-4444-4444-8444-444444444444')
        second = self._tally_op('55555555-5555-4555-8555-555555555555')
        results = self._post('sync', {'ops': [first, second]}).json()['results']
        self.assertEqual([r['status'] for r in results], ['ok', 'rejected'])

    def test_bad_input_is_rejected_not_retried(self):
        op = self._tally_op('66666666-6666-4666-8666-666666666666')
        op['payload']['lines'][0]['bunches_ripe'] = 'many'
        res = self._post('sync', {'ops': [op, {'uuid': '77777777-7777-4777-8777-777777777777', 'type': 'nope'},
                                          {'type': 'harvest_tally'}]}).json()['results']
        self.assertEqual([r['status'] for r in res], ['rejected'] * 3)
        self.assertEqual([r['code'] for r in res], ['bad_request', 'unknown_type', 'bad_request'])

    def test_negative_counts_rejected(self):
        op = self._tally_op('88888888-8888-4888-8888-888888888888', bunches_unripe=-3)
        res = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual(res['status'], 'rejected')

    def test_batch_size_limit(self):
        ops = [{'uuid': str(i), 'type': 'harvest_tally', 'payload': {}} for i in range(201)]
        self.assertEqual(self._post('sync', {'ops': ops}).status_code, 400)
        self.assertEqual(self._post('sync', {'ops': 'x'}).status_code, 400)

    # ---- app shell ----

    def test_shell_manifest_and_service_worker(self):
        res = self.url_open('/plantation/field')
        self.assertEqual(res.status_code, 200)
        self.assertIn('/ss_plantation/static/field/app.js', res.text)

        manifest = self.url_open('/plantation/field/manifest.json').json()
        self.assertEqual(manifest['start_url'], '/plantation/field')

        sw = self.url_open('/plantation/field/sw.js')
        self.assertEqual(sw.status_code, 200)
        self.assertEqual(sw.headers['Service-Worker-Allowed'], '/plantation/field')
        self.assertNotIn('__VERSION__', sw.text)
        self.assertNotIn('__ASSETS__', sw.text)
        self.assertIn('/ss_plantation/static/field/app.js', sw.text)
        self.assertEqual(sw.text, self.url_open('/plantation/field/sw.js').text, "stable version string")

    # ---- transport notes and field activities ----

    def _transport_op(self, uuid, bunches=40, block=None, **payload):
        return {'uuid': uuid, 'type': 'transport_note', 'payload': {
            'date': str(fields.Date.today()), 'harvested_at': '2026-11-03 06:30:00',
            'division_id': self.division.id, 'plate': ' kt 1234 ab ', 'driver_id': self.harvester.id,
            'lines': [{'block_id': (block or self.block).id, 'bunches': bunches}], **payload}}

    def test_transport_note_synced_as_draft_and_replay_is_harmless(self):
        op = self._transport_op('a1111111-1111-4111-8111-111111111111')
        res = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual(res['status'], 'ok')
        note = self.env['ss.plantation.transport'].browse(res['id'])
        self.assertEqual(note.state, 'draft')
        self.assertEqual(note.plate, 'KT 1234 AB', "the plate is tidied up")
        self.assertEqual(note.driver_id, self.harvester)
        self.assertEqual(str(note.harvested_at), '2026-11-03 06:30:00')
        self.assertEqual(note.bunch_total, 40)
        self.assertEqual(note.field_device_id, self.device)
        again = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual((again['status'], again['id']), ('duplicate', note.id))
        self.assertEqual(self.env['ss.plantation.transport'].search_count(
            [('client_uuid', '=', op['uuid'])]), 1)

    def test_transport_note_rejections(self):
        other_division = self.env['ss.plantation.division'].create({
            'name': 'Afdeling II', 'code': 'D2', 'estate_id': self.estate.id})
        foreign = self.env['ss.plantation.block'].create({
            'name': 'Block X', 'code': 'TX01', 'division_id': other_division.id, 'area_ha': 5.0,
            'avg_bunch_weight_kg': 15.0, 'stage': 'mature'})
        ops = [
            self._transport_op('a2222222-2222-4222-8222-222222222222', block=foreign),
            self._transport_op('a3333333-3333-4333-8333-333333333333', bunches=0),
            self._transport_op('a4444444-4444-4444-8444-444444444444', lines=[]),
            self._transport_op('a5555555-5555-4555-8555-555555555555', harvested_at='not a time'),
            self._transport_op('a6666666-6666-4666-8666-666666666666'),
        ]
        results = self._post('sync', {'ops': ops}).json()['results']
        self.assertEqual([r['status'] for r in results], ['rejected'] * 4 + ['ok'])
        self.assertEqual(results[0]['code'], 'validation')
        self.assertEqual(results[3]['code'], 'bad_request')
        self.assertFalse(self.env['ss.plantation.transport'].search(
            [('client_uuid', 'in', [o['uuid'] for o in ops[:4]])]))

    def _activity_op(self, uuid, act_type, **payload):
        return {'uuid': uuid, 'type': 'field_activity', 'payload': {
            'date': str(fields.Date.today()), 'block_id': self.block.id, 'type_id': act_type.id,
            'man_days': 3, 'employee_ids': [self.harvester.id, self.harvester_2.id], 'note': 'Round 2',
            **payload}}

    def test_field_activity_synced_as_draft_with_inputs(self):
        Type = self.env['ss.plantation.activity.type']
        fert = Type.create({'name': 'Fertilising T', 'uom_basis': 'ha', 'requires_inputs': True})
        npk = self.env['product.product'].sudo().create({'name': 'NPK T', 'type': 'consu', 'is_storable': True})
        op = self._activity_op('b1111111-1111-4111-8111-111111111111', fert,
                               inputs=[{'product_id': npk.id, 'qty': 120.0}])
        res = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual(res['status'], 'ok', res)
        act = self.env['ss.plantation.activity'].browse(res['id'])
        self.assertEqual(act.state, 'draft', "stock is only used when the supervisor marks it Done")
        self.assertEqual(act.quantity, self.block.area_ha, "hectare-based types default to the block area")
        self.assertEqual(act.man_days, 3)
        self.assertEqual(act.employee_ids, self.harvester + self.harvester_2)
        self.assertEqual(act.input_line_ids.product_id, npk)
        self.assertEqual(act.input_line_ids.qty, 120.0)
        self.assertEqual(act.field_device_id, self.device)
        again = self._post('sync', {'ops': [op]}).json()['results'][0]
        self.assertEqual((again['status'], again['id']), ('duplicate', act.id))

    def test_field_activity_rejections(self):
        Type = self.env['ss.plantation.activity.type']
        plain = Type.create({'name': 'Weeding T', 'uom_basis': 'ha', 'requires_inputs': False})
        npk = self.env['product.product'].sudo().create({'name': 'NPK U', 'type': 'consu', 'is_storable': True})
        ops = [
            self._activity_op('b2222222-2222-4222-8222-222222222222', plain,
                              inputs=[{'product_id': npk.id, 'qty': 5.0}]),  # type does not use inputs
            self._activity_op('b3333333-3333-4333-8333-333333333333', plain,
                              inputs=[{'product_id': npk.id, 'qty': 0}]),
            self._activity_op('b4444444-4444-4444-8444-444444444444', plain, man_days=-1),
            self._activity_op('b5555555-5555-4555-8555-555555555555', plain, block_id=0),
            self._activity_op('b6666666-6666-4666-8666-666666666666', plain),
        ]
        results = self._post('sync', {'ops': ops}).json()['results']
        self.assertEqual([r['status'] for r in results], ['rejected'] * 4 + ['ok'], results)
        self.assertFalse(self.env['ss.plantation.activity'].search(
            [('client_uuid', 'in', [o['uuid'] for o in ops[:4]])]))

    def test_bootstrap_has_products_and_input_flag(self):
        Type = self.env['ss.plantation.activity.type']
        fert = Type.create({'name': 'Fertilising V', 'uom_basis': 'ha', 'requires_inputs': True})
        kg = self.env.ref('uom.product_uom_kgm')
        npk = self.env['product.product'].sudo().create({
            'name': 'NPK V', 'type': 'consu', 'is_storable': True, 'uom_id': kg.id})
        service = self.env['product.product'].sudo().create({'name': 'Consult V', 'type': 'service'})
        data = self._get('bootstrap').json()['data']
        products = {p['id']: p for p in data['products']}
        self.assertEqual(products[npk.id]['uom_name'], kg.name)
        self.assertNotIn(service.id, products, "only storable products can be inputs")
        types = {t['id']: t for t in data['activity_types']}
        self.assertTrue(types[fert.id]['requires_inputs'])
