# Offline Field App — Spec (draft v0.1)

Module: `ss_plantation` (Odoo 20). Status: phase 1 built and deployed to the dev instance (https://sawit.kpmgroup.co.id). See section 12.

## 1. Goal and scope

Let field staff record work with **no signal** and sync later. Standalone PWA served by Odoo
(not the Odoo web client).

| Role | Records | Where | Offline |
|---|---|---|---|
| Kerani panen (tally clerk) at TPH | Harvest tally: per worker per day, block, bunches | TPH, phone | Yes (pilot) |
| Mandor | Field activity (spraying, fertilising, ...) | Block, phone | Yes (phase 3) |
| Kerani / mandor | Transport note (TPH -> truck) | TPH, phone | Yes (phase 3) |
| Weighbridge operator | Weigh ticket | Mill | Out of scope (online) |

Out of scope: payroll, reports, mill OER/KER, weigh tickets.

Confirmed by the user: tally is per worker per day, recorded at the TPH, mandor carries a phone,
assume no signal. Devices: personal or company, Android and iPhone.

## 2. Existing models used (no redesign)

- `ss.plantation.harvest.tally` (date, division, clerk, state draft/confirmed/cancel) with
  `...tally.line` (block, harvester, ripe/unripe/overripe bunches, loose fruit kg). Existing
  constraints: block must be in the division and mature; one line per harvester/block/day.
- `ss.plantation.transport` (+ lines per block, vehicle, driver, state draft/sent/weighed).
- `ss.plantation.activity` (block, type, quantity, man-days, workers, inputs, state draft/done).

The app only ever creates **drafts**. Confirming/closing stays in the Odoo backend by the
estate admin, who reviews synced data first.

## 3. Architecture

- Route `/plantation/field` serves a minimal HTML shell. The app is plain ES modules in
  `static/field/` (not an Odoo asset bundle, not OWL: bundle hashes change per database and
  would make the offline cache fragile). Manifest at `/plantation/field/manifest.json`.
- Service worker at `/plantation/field/sw.js`, header `Service-Worker-Allowed: /plantation/field`.
  Precaches shell, JS, CSS; versioned cache name; update prompt on new version.
- Local storage: IndexedDB with stores `master`, `outbox`, `photos`, `meta`.
- **Requires HTTPS.** Service workers do not run on plain `http://IP:port`. A subdomain + TLS on
  the plantation instance is a prerequisite for phase 1.

## 4. Master data cache

Per-user scope (the user's divisions/estates, their company).

| Store | Records | Fields |
|---|---|---|
| divisions, blocks | mature blocks of allowed divisions | id, name, division_id, stage, area_ha |
| harvesters / workers | employees of the gang(s) | id, name, badge |
| activity types, FFB grades | all active | id, name, uom_basis |
| vehicles, drivers | active | id, plate, name |
| landmarks (TPH) | TPH landmarks | id, name, lat, lon |

- `GET /plantation/field/api/bootstrap` -> full snapshot + `server_time` + `schema_version`.
- `GET /plantation/field/api/delta?since=<server_time>` -> changed rows (`write_date`) and
  `removed` ids (archived/unlinked). Client stores `server_time` returned by the server, never
  its own clock.
- Refresh on app open and manual button. If the cache is older than N days (default 7),
  show a warning but still allow entry.

## 5. Sync protocol

Outbox entry: `{uuid, type, payload, created_at, status, attempts, error}`.

- `uuid` is generated on the phone (crypto.randomUUID). Server models get a `client_uuid`
  Char field with a SQL unique index (per company) on tally, tally line, transport, activity.
- `POST /plantation/field/api/sync` takes an ordered batch, returns per-operation results:
  - `ok` (created) or `duplicate` (uuid already exists, returns existing id; treated as ok)
  - `rejected` with a stable `code` and a translated message (e.g. harvester already tallied on
    that block today, block not mature, block outside division)
- Retry rules: network error, timeout, 5xx -> stay in outbox, exponential backoff.
  `rejected` -> move to the **Needs attention** screen; user edits and resubmits (same uuid).
- Order: parent before lines; photos after their record syncs.
- Triggers: app open, window `focus`, `online` event, manual "Sync now", and Background Sync
  where supported (Android Chrome). iOS has no Background Sync: the other triggers cover it.
- Conflicts: records are append-only drafts, so conflicts are rare. Duplicate
  harvester/block/day is handled by the existing server constraint -> `rejected`, shown to the
  clerk with the existing record's reference.

## 6. Authentication

- Device registration: user signs in online once (normal Odoo login) -> server issues a
  long-lived device token (stored hashed, tied to user + device name, revocable in backend
  under a new model `ss.plantation.field.device`).
- App opens offline without login. Optional device PIN for shared phones.
- Every API call is authorised with the token and runs `with_user(user)` so normal Odoo record
  rules and access rights apply. Revoking the device stops sync; unsynced data is kept on the
  phone and flagged.
- Token expiry: default 90 days, renewed on each successful sync.

## 7. Screens (phase 1 + pilot)

1. Home: sync status (pending count, last sync, cache age), buttons Tally / Needs attention.
2. Tally list (today, by division) and Tally form: date, division, TPH, then add lines:
   harvester (searchable), block, ripe / unripe / overripe bunches, loose fruit kg.
   Local validation: block belongs to division, mature, no duplicate harvester/block/day,
   non-negative numbers.
3. Needs attention: rejected entries with reason and an edit button.
4. Settings: device name, PIN, clear local data (blocked if outbox not empty).

Large touch targets, numeric keypad inputs, usable one-handed in sunlight (high contrast).
Indonesian is the default language; strings go through Odoo translation.

## 8. Phases

1. Foundation: HTTPS + subdomain, PWA shell, service worker, device auth, bootstrap/delta,
   outbox, sync endpoint, status UI.
2. Pilot: harvest tally screens, `client_uuid` + backend "synced from app" indicator, admin
   review list of app-created drafts.
3. Transport note and field activity (including inputs and workers).
4. Photos, GPS capture at entry time, conflict screen polish; optional barcode/QR scan.
5. Field test on real phones in airplane mode.

## 9. Testing

- Python unit tests: sync endpoint idempotency (replay same batch -> no duplicates), rejection
  codes, token revoke, delta correctness incl. removed ids, record rules per user.
- Playwright: login once, load app, `context.set_offline(True)`, enter tally lines, reload
  page offline (shell still loads), reconnect, verify records appear once in the backend;
  repeat with an injected rejection and a mid-batch network failure.
- Manual: real Android and iPhone, airplane mode, 2-day offline run, low-storage case.

## 10. Risks

- No HTTPS -> no service worker. Needs subdomain + certificate (phase 1 prerequisite).
- iOS: no Background Sync; Safari may evict data of unused PWAs (about 7 days, not verified
  for IndexedDB) -> warn when unsynced entries are older than 3 days.
- Photos can exhaust storage -> compress, cap count, delete after sync.
- Wrong-worker entry at TPH -> mitigated by local duplicate check and admin review before
  confirm; no auto-confirm.
- Time zone / date drift on phones -> `date` is a user-visible field; `created_at` is
  informational only.

## 11. Open questions

1. Does the TPH clerk record the worker from a paper list, or does the worker's name/ID card
   (barcode/NFC) identify them? Affects phase 4.
2. Is the TPH recorded per entry? (A `tph_id` landmark on the tally line would be a small
   model addition.)
3. Is fruit grading (ripe/unripe/overripe) done at the TPH by the clerk? (The existing tally
   assumes yes.)
4. Who may edit a draft after sync: the clerk through the app, or only the backend?
5. Subdomain name and DNS owner.

## 12. Phase 1 as built

- Backend: `ss.plantation.field.device` (hashed token, expiry slides on each sync, revoke by
  unticking Active; menu Configuration > Field Devices), `client_uuid` (unique per company) and
  `field_device_id` on the tally, controllers in `controllers/field.py`.
- Pairing: the phone opens `/plantation/field`, taps Pair, is sent to the normal Odoo login
  (passwords and 2FA work as usual), returns and receives its token. Harvester names and badges
  are read with sudo, limited to the user's companies, because employee barcodes are HR-only.
- Sync: harvest tally only (`type: harvest_tally`). Each entry runs in its own savepoint; results
  are `ok`, `duplicate`, `rejected` (with code and message) or `error` (retried with backoff).
  Coming back online or into view retries at once; offline, no attempts are made.
- App: pair, home, tally list/form (local checks: required fields, no negatives, no duplicate
  worker/block/day), Needs attention, Settings (language id/en, refresh data, unpair).
- Tests: `tests/test_field_app.py` (12 backend tests) and `e2e/offline_field.py` (12 browser
  checks, offline included).
- Not yet: transport note, field activity, photos, GPS, device PIN, QR/barcode scan.
- Needs HTTPS to install: the browser test maps the hostname to the server IP until public DNS
  catches up.
