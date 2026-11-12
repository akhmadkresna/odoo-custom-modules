import * as db from './db.js';
import { call, ApiError } from './api.js';
import * as sync from './sync.js';
import { t, ago, setLang, getLang } from './i18n.js';

const APP_PATH = '/plantation/field';
const root = document.getElementById('app');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const today = () => new Date().toLocaleDateString('sv');
const num = (v) => (v === '' || v == null ? 0 : Number(v));

const ui = { view: 'boot', paired: false, user: null, form: null, notice: null, swUpdated: false, pairError: null, busy: false };
let cache = { divisions: [], blocks: [], harvesters: [] };
let outbox = [];

async function loadCache() {
  cache = {
    divisions: (await sync.master('divisions')).sort((a, b) => a.name.localeCompare(b.name)),
    blocks: (await sync.master('blocks')).sort((a, b) => a.code.localeCompare(b.code)),
    harvesters: (await sync.master('harvesters')).sort((a, b) => a.name.localeCompare(b.name)),
  };
}

// ---------- layout ----------

function header() {
  const s = sync.state;
  const pill = s.online ? `<span class="pill ok">${t('online')}</span>` : `<span class="pill off">${t('offline')}</span>`;
  const pend = s.pending ? `<span class="badge">${s.pending}</span>` : '';
  return `<header>
    <button class="icon" data-action="home" aria-label="${t('home')}">⌂</button>
    <h1>${t('app')}</h1>${pill}${pend}
    <button class="sync" data-action="sync" ${s.syncing ? 'disabled' : ''}>${s.syncing ? t('syncing') : t('syncNow')}</button>
  </header>${banners()}`;
}

function banners() {
  const s = sync.state;
  const out = [];
  if (ui.swUpdated) out.push(`<div class="banner info">${t('updated')} <button data-action="reload">${t('reload')}</button></div>`);
  if (s.lastError === 'unauthorized') out.push(`<div class="banner err">${t('sessionExpired')}</div>`);
  else if (s.lastError === 'server') out.push(`<div class="banner warn">${t('serverError')}</div>`);
  if (s.oldestPendingAt && Date.now() - s.oldestPendingAt > 3 * 24 * 3600 * 1000) out.push(`<div class="banner warn">${t('warnOldPending')}</div>`);
  if (ui.masterChecked && Date.now() - ui.masterChecked > 7 * 24 * 3600 * 1000) out.push(`<div class="banner warn">${t('warnOldData')}</div>`);
  return out.join('');
}

async function render() {
  outbox = await sync.listOutbox();
  ui.masterChecked = await db.getMeta('master_checked', 0);
  const views = { boot, pair: pairView, home: homeView, tally: tallyView, form: formView, attention: attentionView, settings: settingsView };
  const html = (views[ui.view] || homeView)();
  root.innerHTML = ui.view === 'pair' ? html : header() + `<main>${html}</main>`;
  if (ui.view === 'form') updateResults();
}

function boot() { return `<p class="boot">…</p>`; }

// ---------- pair ----------

function pairView() {
  const name = ui.deviceName ?? defaultDeviceName();
  return `<main class="pair">
    <h1>${t('pairTitle')}</h1>
    <p>${t('pairHelp')}</p>
    <label>${t('deviceName')}<input id="devname" value="${esc(name)}"></label>
    ${ui.pairError ? `<p class="error">${esc(ui.pairError)}</p>` : ''}
    <button class="primary" data-action="pair" ${ui.busy ? 'disabled' : ''}>${ui.busy ? t('pairing') : t('pair')}</button>
    <p class="muted small">${t('language')}: <button class="link" data-action="lang" data-lang="id">Indonesia</button> · <button class="link" data-action="lang" data-lang="en">English</button></p>
  </main>`;
}

function defaultDeviceName() {
  const ua = navigator.userAgent;
  const m = ua.match(/Android[^;]*; ([^)]+)\)/);
  if (m) return m[1].trim();
  return /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : 'Phone';
}

async function doPair() {
  const input = document.getElementById('devname');
  ui.deviceName = input ? input.value : ui.deviceName;
  ui.busy = true; ui.pairError = null; await render();
  try {
    const res = await fetch(APP_PATH + '/api/register', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_name: ui.deviceName }),
    });
    const isJson = (res.headers.get('content-type') || '').includes('application/json');
    if (res.status === 401 || (!isJson && res.status !== 403)) {
      location.href = '/web/login?redirect=' + encodeURIComponent(APP_PATH + '?login=1');
      return;
    }
    if (!res.ok || !isJson) throw new Error('failed');
    const data = await res.json();
    await db.setMeta('token', data.token);
    await db.setMeta('user', data.user);
    await db.setMeta('unauthorized', false);
    ui.paired = true; ui.user = data.user; ui.view = 'home'; ui.busy = false;
    await render();
    await sync.refreshMaster();
    await db.setMeta('last_sync', Date.now());
    await loadCache();
    await sync.refreshCounters();
    sync.startAutoSync();
  } catch (e) {
    ui.pairError = navigator.onLine ? t('pairFailed') : t('needOnline');
    ui.busy = false;
    await render();
  }
  ui.busy = false;
}

// ---------- home ----------

function homeView() {
  const s = sync.state;
  const empty = !cache.divisions.length ? `<p class="banner warn">${sync.state.syncing ? t('loadingData') : t('noData')}</p>` : '';
  return `${empty}<div class="cards">
    <button class="card" data-action="tally"><b>${t('tally')}</b><span>${outbox.filter((e) => e.type === 'harvest_tally' && e.payload.date === today()).length} · ${today()}</span></button>
    <button class="card ${s.attention ? 'alert' : ''}" data-action="attention"><b>${t('attention')}</b><span>${s.attention}</span></button>
    <button class="card" data-action="settings"><b>${t('settings')}</b><span>${t('lastSync')}: ${ago(s.lastSync)}</span></button>
  </div>
  <p class="muted small">${s.pending} ${t('pending')}</p>`;
}

// ---------- tally list ----------

function chip(e) {
  const map = { pending: ['stPending', 'warn'], synced: ['stSynced', 'ok'], rejected: ['stRejected', 'err'] };
  const [label, cls] = map[e.status] || ['stPending', 'warn'];
  return `<span class="chip ${cls}">${t(label)}</span>`;
}

function divisionName(id) { return (cache.divisions.find((d) => d.id === id) || {}).name || '#' + id; }
function totalBunches(p) { return p.lines.reduce((n, l) => n + l.bunches_ripe + l.bunches_overripe, 0); }

function tallyView() {
  const list = outbox.filter((e) => e.type === 'harvest_tally');
  const rows = list.map((e) => `<li>
      <div><b>${esc(e.payload.date)}</b> · ${esc(divisionName(e.payload.division_id))} ${chip(e)}</div>
      <div class="muted small">${e.payload.lines.length} · ${t('total')}: ${totalBunches(e.payload)}${e.server_name ? ' · ' + esc(e.server_name) : ''}</div>
      ${e.status === 'pending' ? `<button class="link" data-action="edit" data-uuid="${e.uuid}">${t('edit')}</button>` : ''}
    </li>`).join('');
  return `<button class="primary block" data-action="new-tally">${t('newTally')}</button>
    ${list.length ? `<ul class="list">${rows}</ul>` : `<p class="muted">${t('empty')}</p>`}`;
}

// ---------- tally form ----------

function newForm(entry) {
  const divisions = cache.divisions;
  const p = entry ? JSON.parse(JSON.stringify(entry.payload)) : { date: today(), division_id: divisions.length === 1 ? divisions[0].id : '', lines: [] };
  return { entry, date: p.date, division_id: p.division_id, lines: p.lines, draft: blankDraft(), error: null };
}
const blankDraft = () => ({ harvester_id: '', harvester_name: '', hq: '', block_id: '', ripe: '', overripe: '', unripe: '', loose: '' });

function formView() {
  const f = ui.form, d = f.draft;
  const blocks = cache.blocks.filter((b) => b.division_id === Number(f.division_id) && b.stage === 'mature');
  const lines = f.lines.map((l, i) => `<li><div><b>${esc(l.harvester_name)}</b> · ${esc(l.block_name)}</div>
      <div class="muted small">${t('ripe')} ${l.bunches_ripe} · ${t('overripe')} ${l.bunches_overripe} · ${t('unripe')} ${l.bunches_unripe} · ${l.loose_fruit_kg} kg</div>
      <button class="link" data-action="del-line" data-i="${i}">${t('remove')}</button></li>`).join('');
  return `<h2>${t('tally')}</h2>
    <label>${t('date')}<input type="date" id="f-date" value="${esc(f.date)}"></label>
    <label>${t('division')}<select id="f-division"><option value="">${t('pick')}</option>
      ${cache.divisions.map((x) => `<option value="${x.id}" ${x.id === Number(f.division_id) ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
    <h3>${t('lines')} (${f.lines.length}) · ${t('total')}: ${f.lines.reduce((n, l) => n + l.bunches_ripe + l.bunches_overripe, 0)}</h3>
    <ul class="list">${lines}</ul>
    <fieldset><legend>${t('addLine')}</legend>
      <label>${t('harvester')}<input id="d-hq" autocomplete="off" placeholder="${t('searchHarvester')}" value="${esc(d.harvester_name || d.hq)}"></label>
      <div id="d-results" class="results"></div>
      <label>${t('block')}<select id="d-block"><option value="">${t('pick')}</option>
        ${blocks.map((b) => `<option value="${b.id}" ${b.id === Number(d.block_id) ? 'selected' : ''}>${esc(b.code)} - ${esc(b.name)}</option>`).join('')}</select></label>
      <div class="grid3">
        <label>${t('ripe')}<input id="d-ripe" inputmode="numeric" value="${esc(d.ripe)}"></label>
        <label>${t('overripe')}<input id="d-overripe" inputmode="numeric" value="${esc(d.overripe)}"></label>
        <label>${t('unripe')}<input id="d-unripe" inputmode="numeric" value="${esc(d.unripe)}"></label>
      </div>
      <label>${t('loose')}<input id="d-loose" inputmode="decimal" value="${esc(d.loose)}"></label>
      <button data-action="add-line">${t('add')}</button>
    </fieldset>
    ${f.error ? `<p class="error">${esc(f.error)}</p>` : ''}
    <div class="actions"><button class="primary" data-action="save-tally">${t('save')}</button><button data-action="tally">${t('cancel')}</button></div>`;
}

function updateResults() {
  const box = document.getElementById('d-results');
  if (!box) return;
  const d = ui.form.draft;
  if (d.harvester_id || !d.hq.trim()) { box.innerHTML = ''; return; }
  const q = d.hq.trim().toLowerCase();
  const hits = cache.harvesters.filter((h) => h.name.toLowerCase().includes(q) || (h.barcode || '').toLowerCase().includes(q)).slice(0, 8);
  box.innerHTML = hits.map((h) => `<button data-action="pick-harvester" data-id="${h.id}">${esc(h.name)}${h.barcode ? ' · ' + esc(h.barcode) : ''}</button>`).join('');
}

function duplicateExists(f, harvesterId, blockId) {
  if (f.lines.some((l) => l.harvester_id === harvesterId && l.block_id === blockId)) return true;
  return outbox.some((e) => e.type === 'harvest_tally' && e.status !== 'rejected' && (!f.entry || e.uuid !== f.entry.uuid)
    && e.payload.date === f.date && e.payload.lines.some((l) => l.harvester_id === harvesterId && l.block_id === blockId));
}

function addLine() {
  const f = ui.form, d = f.draft;
  const harvesterId = Number(d.harvester_id), blockId = Number(d.block_id);
  const ripe = num(d.ripe), over = num(d.overripe), unripe = num(d.unripe), loose = num(d.loose);
  if (!harvesterId) f.error = t('errHarvester');
  else if (!blockId) f.error = t('errBlock');
  else if ([ripe, over, unripe, loose].some((n) => n < 0 || Number.isNaN(n))) f.error = t('errNegative');
  else if (!ripe && !over && !unripe && !loose) f.error = t('errCount');
  else if (duplicateExists(f, harvesterId, blockId)) f.error = t('errDup');
  else {
    const block = cache.blocks.find((b) => b.id === blockId);
    f.lines.push({
      harvester_id: harvesterId, harvester_name: d.harvester_name, block_id: blockId, block_name: block.code,
      bunches_ripe: Math.round(ripe), bunches_overripe: Math.round(over), bunches_unripe: Math.round(unripe), loose_fruit_kg: loose,
    });
    f.draft = { ...blankDraft(), block_id: d.block_id }; // keep the block: the next worker is usually on the same one
    f.error = null;
  }
  return render();
}

async function saveTally() {
  const f = ui.form;
  if (!f.division_id) f.error = t('errDivision');
  else if (!f.lines.length) f.error = t('errLines');
  else {
    const payload = { date: f.date, division_id: Number(f.division_id), lines: f.lines };
    if (f.entry) await sync.resubmit(f.entry, payload);
    else await sync.enqueue('harvest_tally', payload);
    ui.form = null; ui.view = 'tally';
  }
  return render();
}

// ---------- attention ----------

function attentionView() {
  const list = outbox.filter((e) => e.status === 'rejected');
  if (!list.length) return `<p class="muted">${t('empty')}</p>`;
  return `<p class="muted small">${t('attentionHelp')}</p><ul class="list">${list.map((e) => `<li>
    <div><b>${esc(e.payload.date)}</b> · ${esc(divisionName(e.payload.division_id))} ${chip(e)}</div>
    <div class="error small">${esc(e.message)}</div>
    <button data-action="edit" data-uuid="${e.uuid}">${t('resend')}</button>
    <button class="link" data-action="delete-entry" data-uuid="${e.uuid}">${t('remove')}</button></li>`).join('')}</ul>`;
}

// ---------- settings ----------

function settingsView() {
  const s = sync.state;
  return `<ul class="list plain">
    <li>${t('userLabel')}: <b>${esc(ui.user ? ui.user.name : '')}</b></li>
    <li>${t('lastSync')}: ${ago(s.lastSync)}</li>
    <li>${t('dataAge')}: ${ago(ui.masterChecked)}</li>
    <li>${t('version')}: ${esc(ui.version || '')}</li>
    <li>${t('language')}: <button class="link" data-action="lang" data-lang="id">Indonesia</button> · <button class="link" data-action="lang" data-lang="en">English</button></li>
  </ul>
  <button data-action="refresh-data">${t('refreshData')}</button>
  <button class="danger" data-action="unpair">${t('unpair')}</button>
  ${ui.settingsMsg ? `<p class="error">${esc(ui.settingsMsg)}</p>` : ''}`;
}

async function unpair() {
  const open = (await sync.listOutbox()).filter((e) => e.status === 'pending' || e.status === 'rejected');
  if (open.length) { ui.settingsMsg = t('unpairBlocked'); return render(); }
  if (!confirm(t('unpairConfirm'))) return;
  for (const store of ['master', 'outbox', 'meta']) await db.clear(store);
  ui.paired = false; ui.user = null; ui.view = 'pair'; ui.settingsMsg = null;
  await sync.refreshCounters();
  await render();
}

// ---------- events ----------

const actions = {
  home: () => { ui.view = 'home'; ui.form = null; return render(); },
  tally: () => { ui.view = 'tally'; ui.form = null; return render(); },
  attention: () => { ui.view = 'attention'; return render(); },
  settings: () => { ui.view = 'settings'; ui.settingsMsg = null; return render(); },
  sync: async () => { await sync.flush({ force: true }); },
  reload: () => location.reload(),
  pair: doPair,
  'new-tally': () => { ui.form = newForm(null); ui.view = 'form'; return render(); },
  edit: (el) => { const e = outbox.find((x) => x.uuid === el.dataset.uuid); ui.form = newForm(e); ui.view = 'form'; return render(); },
  'add-line': addLine,
  'del-line': (el) => { ui.form.lines.splice(Number(el.dataset.i), 1); return render(); },
  'save-tally': saveTally,
  'pick-harvester': (el) => {
    const h = cache.harvesters.find((x) => x.id === Number(el.dataset.id));
    Object.assign(ui.form.draft, { harvester_id: h.id, harvester_name: h.name });
    return render();
  },
  'delete-entry': async (el) => { await sync.remove(el.dataset.uuid); await render(); },
  'refresh-data': async () => { await db.setMeta('master_time', null); await sync.flush({ force: true }); await loadCache(); await render(); },
  unpair,
  lang: async (el) => { setLang(el.dataset.lang); await db.setMeta('lang', el.dataset.lang); await render(); },
};

root.addEventListener('click', async (ev) => {
  const el = ev.target.closest('[data-action]');
  if (!el || !actions[el.dataset.action]) return;
  ev.preventDefault();
  await actions[el.dataset.action](el);
});

root.addEventListener('input', (ev) => {
  const f = ui.form;
  if (!f) return;
  const id = ev.target.id;
  if (id === 'd-hq') { f.draft.hq = ev.target.value; f.draft.harvester_id = ''; f.draft.harvester_name = ''; updateResults(); }
  else if (id.startsWith('d-')) f.draft[id.slice(2)] = ev.target.value;
  else if (id === 'f-date') f.date = ev.target.value;
});

root.addEventListener('change', (ev) => {
  const f = ui.form;
  if (!f) return;
  if (ev.target.id === 'f-division') { f.division_id = ev.target.value; f.lines = []; f.draft = blankDraft(); render(); }
  else if (ev.target.id === 'd-block') f.draft.block_id = ev.target.value;
});

// ---------- start ----------

async function registerWorker() {
  if (!('serviceWorker' in navigator)) return;
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (hadController) { ui.swUpdated = true; render(); } });
  try {
    const reg = await navigator.serviceWorker.register(APP_PATH + '/sw.js', { scope: APP_PATH });
    ui.version = reg.active ? 'active' : 'installing';
  } catch (e) { /* the app still works online without a service worker */ }
}

async function start() {
  setLang(await db.getMeta('lang', 'id'));
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
  await registerWorker();
  ui.user = await db.getMeta('user');
  ui.paired = !!(await db.getMeta('token'));
  ui.view = ui.paired ? 'home' : 'pair';
  if (ui.paired) await loadCache();
  sync.onChange(async () => { if (ui.view !== 'form' && ui.view !== 'pair') { await loadCache(); await render(); } else if (ui.view === 'form') { /* do not disturb typing */ } });
  await sync.refreshCounters();
  await render();
  if (ui.paired) sync.startAutoSync();
  else if (new URLSearchParams(location.search).has('login')) doPair(); // just signed in: finish pairing
  window.__field = { ui, sync, db }; // handy for debugging and tests
}

start();
