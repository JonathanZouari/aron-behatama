/** ניהול מחירון: עריכה בטבלה, השבתה בלי מחיקה, הגדרות, שמירה כגרסה חדשה. */
import { get, put } from '../api.js';
import { el, date, toast, setBusy, showError } from '../ui.js';
import { mountShell } from './shell.js';

const PERCENT_FIELDS = ['waste_rate', 'vat_rate'];
const SETTINGS_FIELDS = ['waste_rate', 'vat_rate', 'quote_validity_days', 'base_labor_price', 'labor_per_door', 'labor_per_drawer', 'labor_per_shelf',
  'back_material_code', 'door_hardware_code', 'drawer_package_code', 'soft_close_code', 'installation_code'];
const pageAlert = document.getElementById('page-alert');
let book = null;      // המחירון הפעיל (מקור)
let items = [];       // עותק עריכה
let activeTab = 'material';

async function load() {
  try {
    const data = await get('/api/admin/pricebook');
    book = data.active;
    items = book ? book.items.map((i) => ({ ...i })) : [];
    document.getElementById('version').textContent = book ? `· גרסה פעילה ${book.version}` : '· אין מחירון פעיל';
    document.getElementById('demo-alert').replaceChildren(book && book.is_demo ? el('div', { class: 'alert alert-warning', style: 'margin-bottom:0.75rem' }, [el('span', { text: 'מחירון פיתוח לדוגמה — המחירים אינם מחירי שוק מאומתים. בייצור יש להגדיר מחירון אמיתי ולסמן שאומת.' })]) : '');
    renderSettings();
    renderItems();
    document.getElementById('versions').replaceChildren(...data.versions.map((v) => el('tr', {}, [el('td', { text: `v${v.version}` }), el('td', { text: date(v.created_at, true) }), el('td', { text: v.is_active ? 'כן' : '' }), el('td', { text: v.is_demo ? 'דמו' : '' })])));
  } catch (err) { showError(pageAlert, err.message, load); pageAlert.hidden = false; }
}

function renderSettings() {
  const s = book ? book.settings : {};
  for (const f of SETTINGS_FIELDS) {
    const input = document.getElementById(f);
    input.value = PERCENT_FIELDS.includes(f) ? (Number(s[f] ?? 0) * 100).toFixed(2).replace(/\.?0+$/, '') : (s[f] ?? '');
  }
  document.getElementById('confirmed_by_carpenter').checked = Boolean(s.confirmed_by_carpenter);
  document.getElementById('is_demo').checked = Boolean(book && book.is_demo);
}

function renderItems() {
  const rows = document.getElementById('rows');
  const list = items.filter((i) => i.category === activeTab);
  document.getElementById('empty').hidden = list.length > 0;
  rows.replaceChildren(...list.map((item) => {
    const bind = (name, type = 'text') => {
      const input = el('input', { type, value: item[name] ?? '', step: type === 'number' ? '0.01' : null, min: type === 'number' ? '0' : null, 'aria-label': name });
      input.addEventListener('input', () => { item[name] = type === 'number' ? input.value : input.value; });
      return input;
    };
    const soft = el('input', { type: 'checkbox', 'aria-label': 'כולל טריקה שקטה' }); soft.checked = Boolean(item.includes_soft_close);
    soft.addEventListener('change', () => { item.includes_soft_close = soft.checked; });
    const active = el('input', { type: 'checkbox', 'aria-label': 'פעיל' }); active.checked = item.active !== false;
    active.addEventListener('change', () => { item.active = active.checked; renderItems(); });
    return el('tr', { style: item.active === false ? 'opacity:0.55' : '' }, [
      el('td', {}, [bind('code')]), el('td', {}, [bind('name_he')]), el('td', {}, [bind('unit')]),
      el('td', { class: 'num' }, [bind('unit_price', 'number')]),
      el('td', {}, [item.category === 'drawer' || item.category === 'hardware' ? soft : '']),
      el('td', {}, [active, item.active === false ? el('span', { class: 'chip', text: 'מושבת', style: 'margin-inline-start:0.3rem' }) : '']),
      el('td', {}, [item._new ? el('button', { class: 'btn btn-sm btn-ghost', type: 'button', text: 'הסרה', onclick: () => { items = items.filter((x) => x !== item); renderItems(); } }) : el('span', { class: 'muted small', text: 'השבתה שומרת היסטוריה' })]),
    ]);
  }));
}

document.getElementById('add-item').addEventListener('click', () => {
  const unit = { material: 'sqm', back_material: 'sqm', finish: 'sqm', hardware: 'unit', drawer: 'drawer', service: 'fixed', delivery: 'trip' }[activeTab] || 'unit';
  items.push({ id: `new-${Date.now()}`, code: '', category: activeTab, name_he: '', unit, unit_price: '0', active: true, includes_soft_close: false, description_he: null, _new: true });
  renderItems();
});

for (const tab of document.querySelectorAll('#tabs button')) {
  tab.addEventListener('click', () => {
    activeTab = tab.dataset.tab;
    for (const t of document.querySelectorAll('#tabs button')) t.setAttribute('aria-selected', String(t === tab));
    document.getElementById('items-panel').hidden = activeTab === 'settings';
    document.getElementById('settings-panel').hidden = activeTab !== 'settings';
    if (activeTab !== 'settings') renderItems();
  });
}

document.getElementById('save-btn').addEventListener('click', async (e) => {
  const settings = {};
  for (const f of SETTINGS_FIELDS) {
    const raw = document.getElementById(f).value.trim();
    settings[f] = PERCENT_FIELDS.includes(f) ? String(Number(raw) / 100) : (f === 'quote_validity_days' ? Number(raw) : raw);
  }
  settings.confirmed_by_carpenter = document.getElementById('confirmed_by_carpenter').checked;
  const payload = items.filter((i) => i.code.trim()).map(({ _new, ...i }) => ({ ...i, id: _new ? i.code.trim() : i.id, code: i.code.trim(), unit_price: String(i.unit_price) }));
  if (!payload.length) { toast('המחירון חייב לכלול לפחות פריט אחד', 'error'); return; }
  setBusy(e.currentTarget, true);
  try {
    const saved = await put('/api/admin/pricebook', { settings, items: payload, is_demo: document.getElementById('is_demo').checked });
    toast(`נשמרה גרסת מחירון ${saved.version}`, 'success');
    await load();
  } catch (err) {
    const details = err.body && err.body.errors ? ' — ' + Object.values(err.body.errors).join('; ') : '';
    toast(err.message + details, 'error');
  } finally { setBusy(e.currentTarget, false); }
});

mountShell().then((me) => { if (me) load(); });
