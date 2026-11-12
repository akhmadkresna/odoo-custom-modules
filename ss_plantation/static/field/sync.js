import * as db from './db.js';
import { call, ApiError } from './api.js';

export const MASTER_KEYS = ['divisions', 'blocks', 'harvesters', 'activity_types', 'landmarks'];
const SYNCED_KEEP_MS = 3 * 24 * 3600 * 1000;
const BATCH = 50;
const BACKOFF_MS = [0, 5000, 15000, 60000, 300000]; // retry delays by attempt count

export const state = {
  online: navigator.onLine,
  syncing: false,
  pending: 0,
  attention: 0,
  oldestPendingAt: null,
  lastSync: null,
  masterTime: null,
  lastError: null, // 'network' | 'unauthorized' | 'server' | null
};

const bus = new EventTarget();
export const onChange = (fn) => bus.addEventListener('change', fn);
const emit = () => bus.dispatchEvent(new Event('change'));

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15);
    return (c === 'x' ? r : (r & 3) | 8).toString(16);
  });
}

export async function refreshCounters() {
  const rows = await db.all('outbox');
  const open = rows.filter((r) => r.status !== 'synced');
  state.pending = open.filter((r) => r.status === 'pending').length;
  state.attention = open.filter((r) => r.status === 'rejected').length;
  const times = open.filter((r) => r.status === 'pending').map((r) => r.created_at);
  state.oldestPendingAt = times.length ? Math.min(...times) : null;
  state.lastSync = await db.getMeta('last_sync');
  state.masterTime = await db.getMeta('master_time');
  emit();
}

// ---------- reference data ----------

async function applyMaster(payload) {
  for (const key of MASTER_KEYS) {
    const stored = (await db.get('master', key)) || { key, rows: {} };
    const rows = stored.rows;
    for (const row of payload.data[key] || []) {
      if (row.active === false) delete rows[row.id];
      else rows[row.id] = row;
    }
    const visible = new Set(payload.ids[key] || []);
    for (const id of Object.keys(rows)) if (!visible.has(Number(id))) delete rows[id];
    await db.put('master', { key, rows });
  }
  await db.setMeta('master_time', payload.server_time);
}

export async function refreshMaster() {
  const since = await db.getMeta('master_time');
  const payload = await call(since ? 'delta?since=' + encodeURIComponent(since) : 'bootstrap');
  await applyMaster(payload);
  await db.setMeta('master_checked', Date.now());
}

export async function master(key) {
  const row = await db.get('master', key);
  return row ? Object.values(row.rows) : [];
}

// ---------- outbox ----------

export async function enqueue(type, payload) {
  const entry = { uuid: uuid(), type, payload, status: 'pending', created_at: Date.now(), attempts: 0, next_try: 0 };
  await db.put('outbox', entry);
  await refreshCounters();
  flush();
  return entry;
}

export async function resubmit(entry, payload) {
  Object.assign(entry, { payload, status: 'pending', attempts: 0, next_try: 0, message: null });
  await db.put('outbox', entry);
  await refreshCounters();
  flush();
}

export async function listOutbox() {
  return (await db.all('outbox')).sort((a, b) => b.created_at - a.created_at);
}

export async function remove(uuidValue) {
  await db.del('outbox', uuidValue);
  await refreshCounters();
}

async function purgeSynced() {
  const now = Date.now();
  for (const row of await db.all('outbox')) {
    if (row.status === 'synced' && now - row.synced_at > SYNCED_KEEP_MS) await db.del('outbox', row.uuid);
  }
}

let flushing = null;

export function flush({ force = false } = {}) {
  if (!navigator.onLine) return Promise.resolve(); // no point trying, and it would only grow the retry delay
  if (flushing) return flushing;
  flushing = doFlush(force).finally(() => { flushing = null; state.syncing = false; emit(); });
  return flushing;
}

async function doFlush(force) {
  if (!(await db.getMeta('token'))) return;
  state.syncing = true;
  state.lastError = null;
  emit();
  try {
    const now = Date.now();
    const due = (await db.all('outbox'))
      .filter((r) => r.status === 'pending' && (force || r.next_try <= now))
      .sort((a, b) => a.created_at - b.created_at);
    for (let i = 0; i < due.length; i += BATCH) {
      const batch = due.slice(i, i + BATCH);
      let res;
      try {
        res = await call('sync', { method: 'POST', body: { ops: batch.map(({ uuid, type, payload }) => ({ uuid, type, payload })) } });
      } catch (e) {
        if (e instanceof ApiError && e.kind !== 'unauthorized') {
          for (const row of batch) {
            row.attempts += 1;
            row.next_try = Date.now() + BACKOFF_MS[Math.min(row.attempts, BACKOFF_MS.length - 1)];
            await db.put('outbox', row);
          }
        }
        throw e;
      }
      const byUuid = Object.fromEntries(batch.map((r) => [r.uuid, r]));
      for (const r of res.results) {
        const row = byUuid[r.uuid];
        if (!row) continue;
        if (r.status === 'ok' || r.status === 'duplicate') {
          Object.assign(row, { status: 'synced', synced_at: Date.now(), server_name: r.name, server_id: r.id, message: null });
        } else if (r.status === 'rejected') {
          Object.assign(row, { status: 'rejected', message: r.message, code: r.code });
        } else {
          row.attempts += 1; // transient server error: retry later
          row.next_try = Date.now() + BACKOFF_MS[Math.min(row.attempts, BACKOFF_MS.length - 1)];
        }
        await db.put('outbox', row);
      }
    }
    await db.setMeta('last_sync', Date.now());
    await purgeSynced();
    const checked = await db.getMeta('master_checked', 0);
    if (force || Date.now() - checked > 15 * 60 * 1000) await refreshMaster();
  } catch (e) {
    state.lastError = e instanceof ApiError ? e.kind : 'server';
    if (state.lastError === 'unauthorized') await db.setMeta('unauthorized', true);
  } finally {
    await refreshCounters();
  }
}

// ---------- triggers ----------

let autoStarted = false;
export function startAutoSync() {
  if (autoStarted) return;
  autoStarted = true;
  // Coming back online or into view: try at once, ignoring any retry delay from earlier failures.
  const kick = () => { state.online = navigator.onLine; emit(); if (navigator.onLine) flush({ force: true }); };
  window.addEventListener('online', kick);
  window.addEventListener('offline', () => { state.online = false; emit(); });
  window.addEventListener('focus', kick);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) kick(); });
  setInterval(() => { if (navigator.onLine && !document.hidden) flush(); }, 60000);
  kick();
}
