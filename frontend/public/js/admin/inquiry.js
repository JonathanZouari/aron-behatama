/** פרטי פנייה לנגר: עריכת מפרט, חישוב טיוטה, סעיפים ידניים, פרסום, ביטול, הערות והיסטוריה. */
import { get, post, patch } from '../api.js';
import { el, chip, date, money, percent, toast, setBusy, showError, queryParam, askDialog, FIELD_LABELS } from '../ui.js';
import { SpecCard } from '../spec-card.js';
import { mountShell } from './shell.js';

const id = queryParam('id');
const pageAlert = document.getElementById('page-alert');
let detail = null;
let specCard = null;
let pendingPatch = {};
let selectedQuoteId = null;

const EVENT_LABELS = {
  inquiry_created: 'הפנייה נוצרה', spec_updated: 'המפרט עודכן', submitted: 'נשלחה לנגר', access_link_created: 'נוצר קישור גישה',
  quote_draft_created: 'נוצרה טיוטת הצעה', draft_recalculated: 'הטיוטה חושבה מחדש', quote_published: 'הצעה פורסמה ללקוח',
  quote_accepted: 'הלקוח אישר את ההצעה', change_requested: 'הלקוח ביקש שינוי', quote_cancelled: 'הצעה בוטלה',
  inquiry_closed: 'הפנייה נסגרה', customer_linked: 'הפנייה קושרה ללקוח', carpenter_reviewing: 'הנגר מטפל בבקשת השינוי',
};
const ACTOR_LABELS = { customer: 'לקוח', carpenter: 'נגר', system: 'מערכת', ai: 'סוכן AI' };

async function load() {
  pageAlert.hidden = true;
  try {
    detail = await get(`/api/admin/inquiries/${id}`);
    render();
  } catch (err) { showError(pageAlert, err.message, load); pageAlert.hidden = false; }
}

function render() {
  document.getElementById('detail').hidden = false;
  document.getElementById('number').textContent = detail.number;
  document.getElementById('status-chip').replaceChildren(chip(detail.status, detail.status_label));
  document.getElementById('manual-chip').replaceChildren(detail.requires_manual_review ? el('span', { class: 'chip warn', text: '⚠ בדיקה ידנית' }) : '');
  const c = detail.contact;
  document.getElementById('contact').textContent = c.name
    ? `${c.name} · ${c.phone}${c.email ? ' · ' + c.email : ''}${c.city ? ' · ' + c.city : ''}`
    : 'עדיין לא נמסרו פרטי קשר (הלקוח באיסוף פרטים)';
  document.getElementById('reopen-btn').hidden = detail.status !== 'change_requested';
  document.getElementById('close-btn').disabled = detail.status === 'closed';

  renderSpec();
  renderQuotes();
  renderChat();
  renderNotes();
  renderEvents();
}

/* ---- מפרט ---- */
function renderSpec() {
  document.getElementById('spec-version').textContent = `— גרסה ${detail.spec.version}${detail.spec.customer_confirmed ? ' (אושרה על ידי הלקוח)' : ''}`;
  if (!specCard) specCard = new SpecCard(document.getElementById('spec-form'), { catalog: detail.catalog, onChange: (ch) => { pendingPatch = { ...pendingPatch, ...ch }; document.getElementById('save-spec').disabled = false; } });
  specCard.readonly = detail.status === 'closed';
  specCard.render(detail.spec.spec, detail.spec.missing_fields);
  pendingPatch = {};
  document.getElementById('save-spec').disabled = true;
  const panel = document.getElementById('manual-panel');
  const reasons = [...(detail.manual_review_reasons || [])];
  const missing = detail.spec.missing_fields || [];
  if (missing.length) reasons.unshift(`שדות חסרים: ${missing.map((f) => FIELD_LABELS[f]).join(', ')}`);
  panel.replaceChildren(reasons.length ? el('div', { class: 'alert alert-warning' }, [el('div', {}, [el('strong', { text: 'שדות חסרים וסיבות לבדיקה ידנית' }), el('ul', { style: 'margin:0.3rem 0 0;padding-inline-start:1rem' }, reasons.map((r) => el('li', { text: r })))])]) : '');
  const zone = document.getElementById('zone');
  zone.replaceChildren(el('option', { value: '', text: 'אוטומטי לפי העיר' }), ...detail.catalog.filter((x) => x.kind === 'delivery_zone').map((z) => el('option', { value: z.code, text: z.name_he })));
}

document.getElementById('save-spec').addEventListener('click', async (e) => {
  if (!Object.keys(pendingPatch).length) return;
  setBusy(e.currentTarget, true);
  try {
    detail = await patch(`/api/admin/inquiries/${id}/spec`, { expected_version: detail.spec.version, patch: pendingPatch });
    toast('המפרט נשמר. טיוטות קודמות סומנו כלא עדכניות — יש לחשב מחדש.', 'success');
    render();
  } catch (err) { toast(err.message, 'error'); if (err.status === 409) load(); }
  finally { setBusy(e.currentTarget, false); }
});

/* ---- הצעות ---- */
function currentQuote() {
  return detail.quotes.find((q) => q.id === selectedQuoteId) || detail.quotes.at(-1) || null;
}

function renderQuotes() {
  const versions = document.getElementById('versions');
  versions.replaceChildren(...detail.quotes.map((q) => el('button', { type: 'button', class: 'version-pill', 'aria-pressed': String(q.id === (currentQuote() || {}).id), onclick: () => { selectedQuoteId = q.id; renderQuotes(); } }, [`v${q.version} · ${q.status_label}${q.is_stale ? ' · לא עדכני' : ''}`])));
  const q = currentQuote();
  const area = document.getElementById('quote-area');
  const stale = document.getElementById('stale-alert');
  stale.replaceChildren();
  document.getElementById('publish-btn').disabled = !(q && q.status === 'draft' && !q.is_stale && q.total !== null);
  document.getElementById('cancel-quote-btn').hidden = !(q && (q.status === 'draft' || q.status === 'published'));
  document.getElementById('recalc-btn').disabled = detail.status === 'closed';
  if (!q) { area.replaceChildren(el('p', { class: 'muted', text: 'עדיין לא חושבה טיוטה. לחצו ״חישוב טיוטה״.' })); renderAdjustments([]); return; }
  if (q.is_stale) stale.append(el('div', { class: 'alert alert-warning' }, [el('span', { text: 'המפרט שונה מאז החישוב — יש לחשב מחדש לפני פרסום.' })]));
  document.getElementById('pricebook-version').textContent = `גרסת מחירון ${q.pricing.pricebook_version}`;
  const tbody = el('tbody', {}, q.items.map((i) => el('tr', {}, [
    el('td', {}, [i.description, i.kind === 'manual' ? el('div', { class: 'muted small', text: `הסבר: ${i.reason}` }) : '']),
    el('td', { class: 'num', text: Number(i.quantity).toLocaleString('he-IL', { maximumFractionDigits: 3 }) }),
    el('td', { class: 'num', text: money(i.unit_price) }), el('td', { class: 'num', text: money(i.total) }),
  ])));
  const manual = q.pricing.manual_required || [];
  area.replaceChildren(
    el('div', { class: 'row spread' }, [chip(q.status, q.status_label), el('span', { class: 'muted small', text: q.published_at ? `פורסמה ${date(q.published_at, true)} · בתוקף עד ${date(q.expires_at)}` : `נוצרה ${date(q.created_at, true)}` })]),
    q.change_request_text ? el('div', { class: 'alert alert-info', style: 'margin:0.5rem 0' }, [el('span', {}, [el('strong', { text: 'בקשת שינוי מהלקוח: ' }), q.change_request_text])]) : '',
    el('div', { class: 'table-wrap' }, [el('table', {}, [el('thead', {}, [el('tr', {}, [el('th', { text: 'תיאור' }), el('th', { class: 'num', text: 'כמות' }), el('th', { class: 'num', text: 'מחיר יח׳' }), el('th', { class: 'num', text: 'סה״כ' })])]), tbody])]),
    manual.length ? el('div', { class: 'alert alert-warning', style: 'margin-top:0.5rem' }, [el('div', {}, [el('strong', { text: 'דרישות שלא תומחרו אוטומטית:' }), el('ul', { style: 'margin:0.3rem 0 0;padding-inline-start:1rem' }, manual.map((m) => el('li', { text: m })))])]) : '',
    el('div', { class: 'quote-total', style: 'margin-top:0.5rem' }, q.total === null
      ? [el('div', { class: 'total-line grand' }, [el('span', { text: 'אין מחיר סופי' }), el('span', { class: 'muted small', text: 'השלימו את הסעיפים הידניים' })])]
      : [el('div', { class: 'total-line' }, [el('span', { text: 'לפני מע״מ' }), el('span', { text: money(q.subtotal) })]),
        el('div', { class: 'total-line' }, [el('span', { text: `מע״מ (${percent(q.vat_rate)})` }), el('span', { text: money(q.vat_amount) })]),
        el('div', { class: 'total-line grand' }, [el('span', { text: 'סה״כ' }), el('span', { text: money(q.total) })])]),
  );
  if (q.status === 'draft') {
    renderAdjustments(q.adjustments || []);
    document.getElementById('zone').value = q.delivery_zone_code || '';
    document.getElementById('manual-handled').checked = Boolean(q.manual_handled);
  }
}

function renderAdjustments(list) {
  const host = document.getElementById('adjustments');
  host.replaceChildren(...list.map((a) => adjustmentRow(a)));
}
function adjustmentRow(a = {}) {
  const row = el('div', { class: 'adjust-row' }, [
    el('div', { class: 'field' }, [el('label', { text: 'תיאור' }), el('input', { name: 'description', value: a.description || '', maxlength: 200 })]),
    el('div', { class: 'field' }, [el('label', { text: 'סכום (₪, שלילי להנחה)' }), el('input', { name: 'amount', type: 'number', step: '0.01', value: a.amount ?? '' })]),
    el('div', { class: 'field' }, [el('label', { text: 'הסבר (חובה)' }), el('input', { name: 'reason', value: a.reason || '', maxlength: 500 })]),
    el('button', { class: 'btn btn-sm btn-ghost', type: 'button', text: 'הסרה', onclick: () => row.remove() }),
  ]);
  return row;
}
document.getElementById('add-adj').addEventListener('click', () => document.getElementById('adjustments').append(adjustmentRow()));

function collectAdjustments() {
  const out = [];
  for (const row of document.querySelectorAll('#adjustments .adjust-row')) {
    const g = (n) => row.querySelector(`[name="${n}"]`).value.trim();
    if (!g('description') && !g('amount')) continue;
    if (!g('reason')) throw new Error('כל סעיף ידני חייב הסבר');
    out.push({ description: g('description'), amount: g('amount'), reason: g('reason') });
  }
  return out;
}

document.getElementById('recalc-btn').addEventListener('click', async (e) => {
  if (Object.keys(pendingPatch).length) { toast('שמרו קודם את שינויי המפרט', 'error'); return; }
  setBusy(e.currentTarget, true);
  try {
    const body = { adjustments: collectAdjustments(), delivery_zone_code: document.getElementById('zone').value || null, manual_handled: document.getElementById('manual-handled').checked };
    const q = await post(`/api/admin/inquiries/${id}/quotes/recalculate`, body);
    selectedQuoteId = q.id;
    toast(q.total === null ? 'הטיוטה חושבה — יש דרישות שדורשות תמחור ידני' : 'הטיוטה חושבה', 'success');
    await load();
  } catch (err) { toast(err.message, 'error'); } finally { setBusy(e.currentTarget, false); }
});

document.getElementById('publish-btn').addEventListener('click', async (e) => {
  const q = currentQuote(); if (!q) return;
  const ok = await askDialog({ title: `פרסום הצעה v${q.version} ללקוח`, message: 'ההצעה תהיה זמינה בעמוד המעקב של הלקוח. לא נשלח דוא״ל.', confirmLabel: 'פרסום' });
  if (ok === null) return;
  setBusy(e.currentTarget, true);
  try { await post(`/api/admin/inquiries/${id}/quotes/publish`, { quote_id: q.id }); toast('ההצעה פורסמה וזמינה ללקוח', 'success'); await load(); }
  catch (err) { toast(err.message, 'error'); } finally { setBusy(e.currentTarget, false); }
});

document.getElementById('cancel-quote-btn').addEventListener('click', async (e) => {
  const q = currentQuote(); if (!q) return;
  const reason = await askDialog({ title: `ביטול הצעה v${q.version}`, withReason: true, confirmLabel: 'ביטול ההצעה', danger: true }); if (reason === null) return;
  setBusy(e.currentTarget, true);
  try { await post(`/api/admin/inquiries/${id}/quotes/cancel`, { quote_id: q.id, reason }); toast('ההצעה בוטלה'); await load(); }
  catch (err) { toast(err.message, 'error'); } finally { setBusy(e.currentTarget, false); }
});

document.getElementById('close-btn').addEventListener('click', async (e) => {
  const reason = await askDialog({ title: 'סגירת הפנייה', message: 'פנייה סגורה אינה ניתנת לעריכה.', withReason: true, confirmLabel: 'סגירה', danger: true }); if (reason === null) return;
  setBusy(e.currentTarget, true);
  try { await post(`/api/admin/inquiries/${id}/close`, { reason }); toast('הפנייה נסגרה'); await load(); }
  catch (err) { toast(err.message, 'error'); } finally { setBusy(e.currentTarget, false); }
});
document.getElementById('reopen-btn').addEventListener('click', async (e) => {
  setBusy(e.currentTarget, true);
  try { await post(`/api/admin/inquiries/${id}/reopen`); await load(); } catch (err) { toast(err.message, 'error'); } finally { setBusy(e.currentTarget, false); }
});

/* ---- שיחה / הערות / היסטוריה ---- */
function renderChat() {
  const host = document.getElementById('tab-chat');
  host.replaceChildren(...(detail.messages.length ? detail.messages.map((m) => el('div', { class: `bubble ${m.role}` }, [m.content, el('span', { class: 'meta', text: `${date(m.created_at, true)}${m.meta && m.meta.simulated ? ' · סוכן מדומה' : ''}` })])) : [el('p', { class: 'muted', text: 'אין הודעות — הלקוח מילא את המפרט בטופס בלבד.' })]));
}
function renderNotes() {
  document.getElementById('notes-list').replaceChildren(...(detail.notes.length ? detail.notes.map((n) => el('div', { class: 'note' }, [n.body, el('span', { class: 'when', text: date(n.created_at, true) })])) : [el('p', { class: 'muted small', text: 'אין הערות עדיין.' })]));
}
function renderEvents() {
  document.getElementById('events').replaceChildren(...detail.events.map((ev) => el('li', {}, [
    el('strong', { text: EVENT_LABELS[ev.event_type] || ev.event_type }), ` · ${ACTOR_LABELS[ev.actor_type] || ev.actor_type}`,
    ev.payload && ev.payload.quote_version ? ` · הצעה v${ev.payload.quote_version}` : '',
    ev.payload && ev.payload.version ? ` · מפרט גרסה ${ev.payload.version}` : '',
    ev.payload && ev.payload.text ? el('div', { class: 'muted small', text: `״${ev.payload.text}״` }) : '',
    el('span', { class: 'when', text: date(ev.created_at, true) }),
  ])));
}
document.getElementById('note-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = document.getElementById('note-text').value.trim(); if (!text) return;
  try { await post(`/api/admin/inquiries/${id}/notes`, { body: text }); document.getElementById('note-text').value = ''; await load(); document.querySelector('[data-tab="notes"]').click(); }
  catch (err) { toast(err.message, 'error'); }
});
for (const tab of document.querySelectorAll('.tabs button')) {
  tab.addEventListener('click', () => {
    for (const t of document.querySelectorAll('.tabs button')) t.setAttribute('aria-selected', String(t === tab));
    for (const name of ['chat', 'notes', 'history']) document.getElementById(`tab-${name}`).hidden = name !== tab.dataset.tab;
  });
}

mountShell().then((me) => { if (me) { if (!id) { location.replace('/admin/dashboard.html'); return; } load(); } });
