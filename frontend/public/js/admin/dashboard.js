/** לוח בקרה: מונים מתוך בסיס הנתונים וטבלת פניות עם חיפוש וסינון. */
import { get } from '../api.js';
import { el, chip, date, money, showError } from '../ui.js';
import { mountShell } from './shell.js';

const rows = document.getElementById('rows');
const pageAlert = document.getElementById('page-alert');
let timer = null;
let requestSeq = 0; // מונע תשובה ישנה ואיטית מלדרוס סינון חדש

async function loadKpis() {
  const d = await get('/api/admin/dashboard');
  const items = [
    ['פניות חדשות', d.new_inquiries], ['ממתינות לבדיקה', d.awaiting_review],
    ['הצעות שפורסמו', d.published_quotes], ['הצעות שאושרו', d.accepted_quotes],
  ];
  document.getElementById('kpis').replaceChildren(...items.map(([label, value]) => el('div', { class: 'kpi' }, [
    el('div', { class: 'value', text: String(value) }), el('div', { class: 'label', text: label }),
  ])));
}

async function loadRows() {
  const params = new URLSearchParams();
  const q = document.getElementById('q').value.trim();
  const status = document.getElementById('status').value;
  if (q) params.set('q', q);
  if (status) params.set('status', status);
  if (document.getElementById('manual').checked) params.set('manual', '1');
  const seq = ++requestSeq;
  const list = await get(`/api/admin/inquiries?${params}`);
  if (seq !== requestSeq) return; // הגיעה בקשה חדשה יותר בינתיים
  document.getElementById('count').textContent = `${list.length} פניות`;
  document.getElementById('empty').hidden = list.length > 0;
  rows.replaceChildren(...list.map((i) => {
    const d = i.dimensions;
    const dims = [d.width_cm, d.height_cm, d.depth_cm].map((v) => v ?? '?').join('×');
    const tr = el('tr', { class: 'clickable', tabindex: 0, role: 'link', 'aria-label': `פנייה ${i.number}` }, [
      el('td', {}, [el('strong', { text: i.number })]),
      el('td', { text: date(i.submitted_at || i.created_at) }),
      el('td', {}, [el('div', { text: i.contact_name || '—' }), el('div', { class: 'muted small', text: i.contact_phone || '', style: 'direction:ltr;text-align:end' })]),
      el('td', { text: dims }),
      el('td', {}, [chip(i.status, i.status_label)]),
      el('td', { class: 'num', text: i.latest_quote && i.latest_quote.total !== null ? money(i.latest_quote.total) : '—' }),
      el('td', {}, [i.requires_manual_review ? el('span', { class: 'chip warn', text: '⚠ בדיקה ידנית' }) : '']),
    ]);
    const open = () => { location.href = `/admin/inquiry.html?id=${i.id}`; };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(); });
    return tr;
  }));
}

async function loadAll() {
  pageAlert.hidden = true;
  try { await Promise.all([loadKpis(), loadRows()]); }
  catch (err) { showError(pageAlert, err.message, loadAll); pageAlert.hidden = false; }
}

document.getElementById('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(loadRows, 300); });
document.getElementById('status').addEventListener('change', loadRows);
document.getElementById('manual').addEventListener('change', loadRows);
document.getElementById('refresh').addEventListener('click', loadAll);

mountShell().then((me) => { if (me) loadAll(); });
