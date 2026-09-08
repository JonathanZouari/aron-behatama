/** לקוחות: רשימה, פרטים והיסטוריה, קישור מפורש של פנייה ללקוח. */
import { get, post } from '../api.js';
import { el, chip, date, money, toast, showError } from '../ui.js';
import { mountShell } from './shell.js';

const pageAlert = document.getElementById('page-alert');
let selectedId = null;
let linkingInquiry = null;
let timer = null;

async function loadList() {
  const q = document.getElementById('q').value.trim();
  const list = await get(`/api/admin/customers${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  document.getElementById('empty').hidden = list.length > 0;
  document.getElementById('list').replaceChildren(...list.map((c) => el('div', { class: 'list-item', role: 'button', tabindex: 0, 'aria-selected': String(c.id === selectedId), onclick: () => select(c.id), onkeydown: (e) => { if (e.key === 'Enter') select(c.id); } }, [
    el('div', {}, [el('strong', { text: c.full_name }), ' ', el('span', { class: 'muted small', text: c.city || '' })]),
    el('div', { class: 'muted small' }, [el('span', { text: c.phone, style: 'direction:ltr;display:inline-block' }), ` · ${c.inquiry_count} פניות · אחרונה ${date(c.last_inquiry_at)}`]),
  ])));
}

async function select(id) {
  selectedId = id;
  await loadList();
  const c = await get(`/api/admin/customers/${id}`);
  document.getElementById('detail').replaceChildren(
    el('div', { class: 'card-header' }, [el('h2', { text: c.full_name }), el('span', { class: 'muted small', text: `לקוח מאז ${date(c.created_at)}` })]),
    el('dl', { class: 'kv' }, [el('dt', { text: 'טלפון' }), el('dd', { text: c.phone, style: 'direction:ltr;text-align:end' }), el('dt', { text: 'דוא״ל' }), el('dd', { text: c.email || '—' }), el('dt', { text: 'עיר' }), el('dd', { text: c.city || '—' })]),
    el('h3', { text: 'היסטוריית פניות', style: 'margin-top:1rem' }),
    c.inquiries.length ? el('div', { class: 'table-wrap' }, [el('table', {}, [
      el('thead', {}, [el('tr', {}, [el('th', { text: 'מספר' }), el('th', { text: 'תאריך' }), el('th', { text: 'מידות' }), el('th', { text: 'סטטוס' }), el('th', { class: 'num', text: 'מחיר' })])]),
      el('tbody', {}, c.inquiries.map((i) => el('tr', { class: 'clickable', onclick: () => { location.href = `/admin/inquiry.html?id=${i.id}`; } }, [
        el('td', { text: i.number }), el('td', { text: date(i.submitted_at || i.created_at) }),
        el('td', { text: [i.dimensions.width_cm, i.dimensions.height_cm, i.dimensions.depth_cm].map((v) => v ?? '?').join('×') }),
        el('td', {}, [chip(i.status, i.status_label)]), el('td', { class: 'num', text: i.latest_quote ? money(i.latest_quote.total) : '—' }),
      ]))),
    ])]) : el('p', { class: 'muted', text: 'אין פניות משויכות.' }),
  );
}

async function loadUnlinked() {
  const list = await get('/api/admin/customers/unlinked-inquiries');
  document.getElementById('unlinked-empty').hidden = list.length > 0;
  document.getElementById('unlinked').replaceChildren(...list.map((i) => el('tr', {}, [
    el('td', {}, [el('a', { href: `/admin/inquiry.html?id=${i.id}`, text: i.number })]), el('td', { text: i.contact_name || '—' }),
    el('td', { text: i.contact_phone || '—', style: 'direction:ltr;text-align:end' }), el('td', {}, [chip(i.status, i.status_label)]),
    el('td', {}, [el('button', { class: 'btn btn-sm btn-secondary', type: 'button', text: 'קישור ללקוח', onclick: () => openDialog(i) })]),
  ])));
}

/* ---- דיאלוג קישור ---- */
const dialog = document.getElementById('link-dialog');
function openDialog(inquiry) {
  linkingInquiry = inquiry;
  document.getElementById('dlg-number').textContent = inquiry.number;
  document.getElementById('dlg-search').value = '';
  document.getElementById('dlg-results').replaceChildren();
  dialog.showModal();
  searchDialog();
}
async function searchDialog() {
  const q = document.getElementById('dlg-search').value.trim();
  const list = await get(`/api/admin/customers${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  document.getElementById('dlg-results').replaceChildren(...(list.length ? list.map((c) => el('div', { class: 'list-item', role: 'button', tabindex: 0, onclick: () => link({ customer_id: c.id }) }, [el('strong', { text: c.full_name }), ' · ', el('span', { class: 'muted small', text: c.phone })])) : [el('p', { class: 'muted small', text: 'לא נמצאו לקוחות' })]));
}
async function link(body) {
  try {
    await post('/api/admin/customers/link', { inquiry_id: linkingInquiry.id, ...body });
    dialog.close();
    toast('הפנייה קושרה ללקוח', 'success');
    await Promise.all([loadList(), loadUnlinked()]);
  } catch (err) { toast(err.message, 'error'); }
}
document.getElementById('dlg-create').addEventListener('click', () => link({ create_from_contact: true }));
document.getElementById('dlg-close').addEventListener('click', () => dialog.close());
document.getElementById('dlg-search').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(searchDialog, 250); });
document.getElementById('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(loadList, 250); });

mountShell().then(async (me) => {
  if (!me) return;
  try { await Promise.all([loadList(), loadUnlinked()]); } catch (err) { showError(pageAlert, err.message); pageAlert.hidden = false; }
});
