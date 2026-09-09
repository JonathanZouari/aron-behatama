/** צפייה בהצעה, אישור לגרסה מדויקת, בקשת שינוי. */
import { get, post } from './api.js';
import { el, chip, date, money, percent, toast, setBusy, showError, queryParam } from './ui.js';
import { renderSpecGroups } from './spec-view.js';

const pageAlert = document.getElementById('page-alert');
let inquiryId = queryParam('inquiry');
let quote = null;

async function init() {
  try {
    if (!inquiryId) {
      const current = await get('/api/inquiries/current');
      if (!current) { location.replace('/track.html'); return; }
      inquiryId = current.id;
    }
    document.getElementById('back-link').href = `/track.html?inquiry=${inquiryId}`;
    const [catalog, q] = await Promise.all([get('/api/catalog'), get(`/api/inquiries/${inquiryId}/quote`)]);
    document.getElementById('loading').hidden = true;
    if (!q) {
      pageAlert.hidden = false;
      pageAlert.replaceChildren(el('div', { class: 'empty card' }, [
        el('img', { class: 'empty-illustration', src: '/img/empty-state.webp', alt: '', width: 1024, height: 1024 }),
        el('h3', { text: 'עדיין אין הצעת מחיר לפנייה זו' }),
        el('p', { class: 'muted', text: 'הנגר עדיין בודק את הפנייה. נעדכן בעמוד המעקב.' }),
        el('a', { class: 'btn btn-secondary', href: `/track.html?inquiry=${inquiryId}`, text: 'למעקב הפנייה' }),
      ]));
      return;
    }
    quote = q;
    render(catalog);
  } catch (err) {
    document.getElementById('loading').hidden = true;
    showError(pageAlert, err.status === 404 ? 'אין גישה לפנייה זו מדפדפן זה.' : err.message, init);
    pageAlert.hidden = false;
  }
}

function render(catalog) {
  document.getElementById('content').hidden = false;
  document.getElementById('quote-id').textContent = `— גרסה ${quote.version}`;
  document.getElementById('quote-dates').textContent = `פורסמה ${date(quote.published_at)} · בתוקף עד ${date(quote.expires_at)}`;
  document.getElementById('status-chip').replaceChildren(chip(quote.status, quote.status_label));

  const changes = quote.spec_changes || {};
  document.getElementById('changes-note').hidden = !Object.keys(changes).length;
  renderSpecGroups(document.getElementById('spec-groups'), quote.spec, catalog, [], changes);

  const tbody = document.getElementById('items');
  tbody.replaceChildren(...quote.items.map((i) => el('tr', {}, [
    el('td', { text: i.description }),
    el('td', { class: 'num', text: Number(i.quantity).toLocaleString('he-IL', { maximumFractionDigits: 3 }) }),
    el('td', { text: unitLabel(i.unit) }),
    el('td', { class: 'num', text: money(i.unit_price) }),
    el('td', { class: 'num', text: money(i.total) }),
  ])));
  document.getElementById('totals').replaceChildren(
    el('div', { class: 'total-line' }, [el('span', { text: 'סה״כ לפני מע״מ' }), el('span', { text: money(quote.subtotal) })]),
    el('div', { class: 'total-line' }, [el('span', { text: `מע״מ (${percent(quote.vat_rate)})` }), el('span', { text: money(quote.vat_amount) })]),
    el('div', { class: 'total-line grand' }, [el('span', { text: 'סה״כ לתשלום' }), el('span', { text: money(quote.total) })]),
  );
  document.getElementById('terms').textContent = quote.terms_he || '';

  const banner = document.getElementById('banner');
  const actions = document.getElementById('actions');
  banner.replaceChildren();
  actions.hidden = !quote.can_accept;
  if (quote.status === 'accepted') {
    banner.append(el('div', { class: 'alert alert-success' }, [el('span', { text: `ההצעה אושרה ב-${date(quote.accepted_at)}. הנגרייה תיצור קשר להמשך.` })]));
  } else if (quote.status === 'expired') {
    banner.append(el('div', { class: 'alert alert-warning' }, [el('span', { text: 'תוקף ההצעה פג. אפשר לבקש הצעה מעודכנת דרך בקשת שינוי בעמוד המעקב או בפנייה לנגרייה.' })]));
  } else if (quote.change_requested) {
    banner.append(el('div', { class: 'alert alert-info' }, [el('span', { text: 'בקשת השינוי שלכם התקבלה. ההצעה תתעדכן על ידי הנגר ולא ניתן לאשר אותה בשלב זה.' })]));
  }
}

function unitLabel(unit) {
  return { sqm: 'מ״ר', unit: 'יח׳', door: 'דלת', drawer: 'מגירה', fixed: 'קבוע', trip: 'נסיעה' }[unit] || unit;
}

document.getElementById('accept-btn').addEventListener('click', async (e) => {
  setBusy(e.currentTarget, true);
  try {
    quote = await post(`/api/inquiries/${inquiryId}/quote/accept`, { quote_id: quote.id, version: quote.version });
    toast('ההצעה אושרה. תודה!', 'success');
    render(await get('/api/catalog'));
  } catch (err) {
    toast(err.message, 'error');
    if (err.status === 409) init();
  } finally { setBusy(e.currentTarget, false); }
});

document.getElementById('change-btn').addEventListener('click', () => {
  document.getElementById('change-form').hidden = false;
  document.getElementById('change-text').focus();
});
document.getElementById('change-cancel').addEventListener('click', () => { document.getElementById('change-form').hidden = true; });
document.getElementById('change-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = document.getElementById('change-text').value.trim();
  if (text.length < 3) { toast('נא לפרט מה תרצו לשנות', 'error'); return; }
  const btn = document.getElementById('change-submit');
  setBusy(btn, true);
  try {
    quote = await post(`/api/inquiries/${inquiryId}/quote/change-request`, { quote_id: quote.id, message: text });
    document.getElementById('change-form').hidden = true;
    toast('בקשת השינוי נשלחה לנגר', 'success');
    render(await get('/api/catalog'));
  } catch (err) { toast(err.message, 'error'); } finally { setBusy(btn, false); }
});

init();
