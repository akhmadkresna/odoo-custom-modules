// Transport note and field activity: the forms, their checks and the entries they queue.
// The harvest tally keeps its own code in app.js.
import { t } from './i18n.js';
import * as sync from './sync.js';

const num = (v) => (v === '' || v == null ? 0 : Number(v));

export function createEntries({ ui, getCache, getOutbox, render, esc, today }) {
  const cache = () => getCache();
  const byId = (list, id) => list.find((x) => x.id === Number(id));
  const divisionName = (id) => (byId(cache().divisions, id) || {}).name || '#' + id;
  const blockLabel = (id) => { const b = byId(cache().blocks, id); return b ? b.code : '#' + id; };
  const typeName = (id) => (byId(cache().activity_types, id) || {}).name || '#' + id;

  // ---------- a small search-and-pick box, shared by the forms ----------
  // People are offered only from the company of the division or block being recorded.
  const formCompany = () => {
    const f = ui.form;
    const division = f.kind === 'transport' ? byId(cache().divisions, f.division_id)
      : byId(cache().divisions, (byId(cache().blocks, f.block_id) || {}).division_id);
    return division ? division.company_id : null;
  };
  const people = () => { const c = formCompany(); return cache().harvesters.filter((h) => !c || h.company_id === c); };
  const SOURCES = { driver: people, worker: people, product: () => cache().products };
  const labelOf = (key, row) => (key === 'product' ? row.name + (row.uom_name ? ' (' + row.uom_name + ')' : '') : row.name + (row.barcode ? ' · ' + row.barcode : ''));

  function picker(key, label, placeholder) {
    const st = ui.form.pk[key];
    return `<label>${label}<input id="pk-${key}" autocomplete="off" placeholder="${esc(placeholder)}" value="${esc(st.name || st.q)}"></label>
      <div id="pk-${key}-results" class="results"></div>`;
  }

  function updatePicker(key) {
    const box = document.getElementById(`pk-${key}-results`);
    if (!box) return;
    const st = ui.form.pk[key];
    if (st.id || !st.q.trim()) { box.innerHTML = ''; return; }
    const q = st.q.trim().toLowerCase();
    const hits = SOURCES[key]().filter((r) => (r.name || '').toLowerCase().includes(q) || (r.barcode || '').toLowerCase().includes(q) || (r.default_code || '').toLowerCase().includes(q)).slice(0, 8);
    box.innerHTML = hits.map((r) => `<button data-action="pk-pick" data-key="${key}" data-id="${r.id}">${esc(labelOf(key, r))}</button>`).join('');
  }

  const newPk = () => ({ driver: { q: '', id: '', name: '' }, worker: { q: '', id: '', name: '' }, product: { q: '', id: '', name: '', uom: '' } });

  // ---------- list text ----------
  function describe(e) {
    const p = e.payload;
    if (e.type === 'transport_note') {
      const bunches = p.lines.reduce((n, l) => n + l.bunches, 0);
      return { title: t('transport'), head: `<b>${esc(p.date)}</b> · ${esc(divisionName(p.division_id))}${p.plate ? ' · ' + esc(p.plate) : ''}`, meta: `${p.lines.length} · ${t('bunches')}: ${bunches}` };
    }
    if (e.type === 'field_activity') {
      return { title: t('activity'), head: `<b>${esc(p.date)}</b> · ${esc(blockLabel(p.block_id))} · ${esc(typeName(p.type_id))}`, meta: `${t('manDays')}: ${p.man_days || 0} · ${t('workers')}: ${(p.employee_ids || []).length}` };
    }
    return null;
  }

  // ---------- transport note ----------
  const nowTime = () => new Date().toTimeString().slice(0, 5);
  const blankTLine = () => ({ block_id: '', bunches: '' });

  function newTransport(entry) {
    const p = entry ? JSON.parse(JSON.stringify(entry.payload)) : null;
    const divisions = cache().divisions;
    const f = {
      kind: 'transport', entry, pk: newPk(), error: null, draft: blankTLine(),
      date: p ? p.date : today(), time: p ? p.time : nowTime(),
      division_id: p ? p.division_id : (divisions.length === 1 ? divisions[0].id : ''),
      plate: p ? p.plate || '' : '', lines: p ? p.lines : [],
    };
    if (p && p.driver_id) f.pk.driver = { q: '', id: p.driver_id, name: p.driver_name || '' };
    return f;
  }

  function transportView() {
    const f = ui.form, d = f.draft;
    const blocks = cache().blocks.filter((b) => b.division_id === Number(f.division_id) && b.stage === 'mature');
    const lines = f.lines.map((l, i) => `<li><div><b>${esc(l.block_name)}</b> · ${t('bunches')}: ${l.bunches}</div>
      <button class="link" data-action="del-tline" data-i="${i}">${t('remove')}</button></li>`).join('');
    return `<h2>${t('transport')}</h2>
      <label>${t('date')}<input type="date" id="tf-date" value="${esc(f.date)}"></label>
      <label>${t('harvestedAt')}<input type="time" id="tf-time" value="${esc(f.time)}"></label>
      <label>${t('division')}<select id="tf-division"><option value="">${t('pick')}</option>
        ${cache().divisions.map((x) => `<option value="${x.id}" ${x.id === Number(f.division_id) ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
      <label>${t('plate')}<input id="tf-plate" autocomplete="off" autocapitalize="characters" value="${esc(f.plate)}"></label>
      ${picker('driver', t('driver'), t('searchEmployee'))}
      <h3>${t('lines')} (${f.lines.length}) · ${t('total')}: ${f.lines.reduce((n, l) => n + l.bunches, 0)}</h3>
      <ul class="list">${lines}</ul>
      <fieldset><legend>${t('addLine')}</legend>
        <label>${t('block')}<select id="tf-block"><option value="">${t('pick')}</option>
          ${blocks.map((b) => `<option value="${b.id}" ${b.id === Number(d.block_id) ? 'selected' : ''}>${esc(b.code)} - ${esc(b.name)}</option>`).join('')}</select></label>
        <label>${t('bunches')}<input id="tf-bunches" inputmode="numeric" value="${esc(d.bunches)}"></label>
        <button data-action="add-tline">${t('add')}</button>
      </fieldset>
      ${f.error ? `<p class="error">${esc(f.error)}</p>` : ''}
      <div class="actions"><button class="primary" data-action="save-transport">${t('save')}</button><button data-action="list-transport">${t('cancel')}</button></div>`;
  }

  function addTLine() {
    const f = ui.form, d = f.draft;
    const blockId = Number(d.block_id), bunches = num(d.bunches);
    if (!blockId) f.error = t('errBlock');
    else if (!Number.isInteger(bunches) || bunches <= 0) f.error = t('errBunches');
    else if (f.lines.some((l) => l.block_id === blockId)) {
      f.lines.find((l) => l.block_id === blockId).bunches += bunches; f.error = null; f.draft = blankTLine();
    } else {
      f.lines.push({ block_id: blockId, block_name: blockLabel(blockId), bunches });
      f.error = null; f.draft = blankTLine();
    }
    return render();
  }

  async function saveTransport() {
    const f = ui.form;
    if (!f.division_id) f.error = t('errDivision');
    else if (!f.lines.length) f.error = t('errLines');
    else {
      const harvestedAt = new Date(`${f.date}T${f.time || '00:00'}:00`).toISOString().slice(0, 19).replace('T', ' ');
      const payload = {
        date: f.date, time: f.time, harvested_at: harvestedAt, division_id: Number(f.division_id),
        plate: f.plate.trim().toUpperCase(), driver_id: f.pk.driver.id || false, driver_name: f.pk.driver.name, lines: f.lines,
      };
      if (f.entry) await sync.resubmit(f.entry, payload); else await sync.enqueue('transport_note', payload);
      ui.form = null; ui.view = 'list'; ui.listType = 'transport_note';
    }
    return render();
  }

  // ---------- field activity ----------
  function newActivity(entry) {
    const p = entry ? JSON.parse(JSON.stringify(entry.payload)) : null;
    return {
      kind: 'activity', entry, pk: newPk(), error: null, inQty: '',
      date: p ? p.date : today(), block_id: p ? p.block_id : '', type_id: p ? p.type_id : '',
      quantity: p ? String(p.quantity || '') : '', autoQty: !p || !p.quantity, man_days: p ? String(p.man_days || '') : '',
      note: p ? p.note || '' : '', workers: p ? p.workers || [] : [], inputs: p ? p.inputs || [] : [],
    };
  }

  function fillQuantity(f) {
    const type = byId(cache().activity_types, f.type_id), block = byId(cache().blocks, f.block_id);
    if (f.autoQty && type && type.uom_basis === 'ha' && block) f.quantity = String(block.area_ha);
  }

  function activityView() {
    const f = ui.form;
    const type = byId(cache().activity_types, f.type_id);
    const unit = type ? { ha: 'ha', palm: t('palms'), none: '' }[type.uom_basis] : '';
    const workers = f.workers.map((w, i) => `<span class="chip ok">${esc(w.name)} <button class="link" data-action="del-worker" data-i="${i}" aria-label="${t('remove')}">×</button></span>`).join(' ');
    const inputs = f.inputs.map((x, i) => `<li><div><b>${esc(x.name)}</b> · ${x.qty} ${esc(x.uom || '')}</div>
      <button class="link" data-action="del-input" data-i="${i}">${t('remove')}</button></li>`).join('');
    const showInputs = (type && type.requires_inputs) || f.inputs.length;
    const pk = f.pk.product;
    return `<h2>${t('activity')}</h2>
      <label>${t('date')}<input type="date" id="af-date" value="${esc(f.date)}"></label>
      <label>${t('block')}<select id="af-block"><option value="">${t('pick')}</option>
        ${cache().blocks.map((b) => `<option value="${b.id}" ${b.id === Number(f.block_id) ? 'selected' : ''}>${esc(b.code)} - ${esc(b.name)} (${esc(divisionName(b.division_id))})</option>`).join('')}</select></label>
      <label>${t('activityType')}<select id="af-type"><option value="">${t('pick')}</option>
        ${cache().activity_types.map((x) => `<option value="${x.id}" ${x.id === Number(f.type_id) ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
      <div class="grid2">
        <label>${t('quantity')}${unit ? ' (' + esc(unit) + ')' : ''}<input id="af-quantity" inputmode="decimal" value="${esc(f.quantity)}"></label>
        <label>${t('manDays')}<input id="af-man_days" inputmode="decimal" value="${esc(f.man_days)}"></label>
      </div>
      <h3>${t('workers')} (${f.workers.length})</h3>
      <div>${workers}</div>
      ${picker('worker', t('addWorker'), t('searchEmployee'))}
      ${showInputs ? `<h3>${t('stockInputs')}</h3><ul class="list">${inputs}</ul>
        <fieldset><legend>${t('addInput')}</legend>
          ${picker('product', t('product'), t('searchProduct'))}
          <label>${t('qty')}${pk.uom ? ' (' + esc(pk.uom) + ')' : ''}<input id="af-inqty" inputmode="decimal" value="${esc(f.inQty)}"></label>
          <button data-action="add-input">${t('add')}</button>
        </fieldset><p class="muted small">${t('inputsHint')}</p>` : ''}
      <label>${t('note')}<textarea id="af-note" rows="3">${esc(f.note)}</textarea></label>
      ${f.error ? `<p class="error">${esc(f.error)}</p>` : ''}
      <div class="actions"><button class="primary" data-action="save-activity">${t('save')}</button><button data-action="list-activity">${t('cancel')}</button></div>`;
  }

  function addInput() {
    const f = ui.form, pk = f.pk.product, qty = num(f.inQty);
    if (!pk.id) f.error = t('errProduct');
    else if (!(qty > 0)) f.error = t('errInputQty');
    else {
      f.inputs.push({ product_id: pk.id, name: pk.name, uom: pk.uom, qty });
      f.pk.product = { q: '', id: '', name: '', uom: '' }; f.inQty = ''; f.error = null;
    }
    return render();
  }

  async function saveActivity() {
    const f = ui.form;
    const quantity = num(f.quantity), manDays = num(f.man_days);
    if (!f.block_id) f.error = t('errBlock');
    else if (!f.type_id) f.error = t('errType');
    else if (quantity < 0 || manDays < 0 || Number.isNaN(quantity) || Number.isNaN(manDays)) f.error = t('errNegative');
    else {
      const payload = {
        date: f.date, block_id: Number(f.block_id), type_id: Number(f.type_id), quantity, man_days: manDays,
        note: f.note.trim(), employee_ids: f.workers.map((w) => w.id), workers: f.workers,
        inputs: f.inputs.map((x) => ({ product_id: x.product_id, qty: x.qty, name: x.name, uom: x.uom })),
      };
      if (f.entry) await sync.resubmit(f.entry, payload); else await sync.enqueue('field_activity', payload);
      ui.form = null; ui.view = 'list'; ui.listType = 'field_activity';
    }
    return render();
  }

  // ---------- wiring ----------
  const open = (view, form, listType) => { ui.form = form; ui.view = view; ui.listType = listType; return render(); };

  const actions = {
    'new-transport': () => open('tform', newTransport(null), 'transport_note'),
    'new-activity': () => open('aform', newActivity(null), 'field_activity'),
    'list-transport': () => { ui.form = null; ui.view = 'list'; ui.listType = 'transport_note'; return render(); },
    'list-activity': () => { ui.form = null; ui.view = 'list'; ui.listType = 'field_activity'; return render(); },
    'add-tline': addTLine,
    'del-tline': (el) => { ui.form.lines.splice(Number(el.dataset.i), 1); return render(); },
    'save-transport': saveTransport,
    'add-input': addInput,
    'del-input': (el) => { ui.form.inputs.splice(Number(el.dataset.i), 1); return render(); },
    'del-worker': (el) => { ui.form.workers.splice(Number(el.dataset.i), 1); return render(); },
    'save-activity': saveActivity,
    'pk-pick': (el) => {
      const key = el.dataset.key, row = SOURCES[key]().find((r) => r.id === Number(el.dataset.id));
      const f = ui.form;
      if (key === 'worker') {
        if (!f.workers.some((w) => w.id === row.id)) f.workers.push({ id: row.id, name: row.name });
        f.pk.worker = { q: '', id: '', name: '' };
      } else if (key === 'product') f.pk.product = { q: '', id: row.id, name: row.name, uom: row.uom_name || '' };
      else f.pk[key] = { q: '', id: row.id, name: row.name };
      return render();
    },
  };

  function openEdit(entry) {
    return entry.type === 'transport_note' ? open('tform', newTransport(entry), 'transport_note') : open('aform', newActivity(entry), 'field_activity');
  }

  function onInput(ev) {
    const f = ui.form, id = ev.target.id;
    if (!f || !id) return false;
    if (id.startsWith('pk-')) {
      const key = id.slice(3), st = f.pk[key];
      if (!st) return false;
      st.q = ev.target.value; st.id = ''; st.name = ''; if (key === 'product') st.uom = '';
      updatePicker(key); return true;
    }
    if (f.kind === 'transport' && id.startsWith('tf-')) {
      const name = id.slice(3);
      if (name === 'bunches') f.draft.bunches = ev.target.value; else f[name] = ev.target.value;
      return true;
    }
    if (f.kind === 'activity' && id.startsWith('af-')) {
      const name = id.slice(3);
      if (name === 'inqty') f.inQty = ev.target.value;
      else { f[name] = ev.target.value; if (name === 'quantity') f.autoQty = false; }
      return true;
    }
    return false;
  }

  function onChange(ev) {
    const f = ui.form, id = ev.target.id;
    if (!f) return false;
    if (f.kind === 'transport') {
      if (id === 'tf-division') { f.division_id = ev.target.value; f.lines = []; f.draft = blankTLine(); render(); return true; }
      if (id === 'tf-block') { f.draft.block_id = ev.target.value; return true; }
    }
    if (f.kind === 'activity') {
      if (id === 'af-block') { f.block_id = ev.target.value; fillQuantity(f); render(); return true; }
      if (id === 'af-type') { f.type_id = ev.target.value; fillQuantity(f); render(); return true; }
    }
    return false;
  }

  const afterRender = () => { if (ui.form && ui.form.pk) for (const key of Object.keys(ui.form.pk)) updatePicker(key); };

  return { views: { tform: transportView, aform: activityView }, actions, describe, openEdit, onInput, onChange, afterRender };
}
