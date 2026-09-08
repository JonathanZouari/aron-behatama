/** מעקב פנייה: סטטוס, מפרט שנשלח, קישור גישה אישי, מעבר להצעה. */
import { get, post } from './api.js';
import { el, chip, date, toast, setBusy, showError, queryParam } from './ui.js';
import { renderSpecGroups } from './spec-view.js';

const STEPS = [
  { key: 'awaiting_carpenter', label: 'נשלחה' },
  { key: 'review', label: 'בבדיקת הנגר' },
  { key: 'quote_available', label: 'הצעה זמינה' },
  { key: 'accepted', label: 'אושרה' },
];
const STEP_INDEX = { collecting_details: -1, awaiting_carpenter: 1, change_requested: 1, quote_available: 2, accepted: 3, closed: 3 };

const pageAlert = document.getElementById('page-alert');

async function init() {
  const errorParam = queryParam('error');
  if (errorParam === 'invalid_link') {
    showError(pageAlert, 'הקישור אינו בתוקף או שבוטל. אם יש לכם פנייה פעילה בדפדפן זה, היא תוצג למטה.');
    pageAlert.hidden = false;
  }
  try {
    const id = queryParam('inquiry');
    const [catalog, inquiry] = await Promise.all([get('/api/catalog'), id ? get(`/api/inquiries/${id}`) : get('/api/inquiries/current')]);
    document.getElementById('loading').hidden = true;
    if (!inquiry) {
      document.getElementById('content').hidden = true;
      pageAlert.hidden = false;
      pageAlert.replaceChildren(el('div', { class: 'empty card' }, [
        el('h3', { text: 'לא נמצאה פנייה בדפדפן זה' }),
        el('p', { class: 'muted', text: 'אם קיבלתם קישור אישי, פתחו אותו. אחרת אפשר להתחיל תכנון חדש.' }),
        el('a', { class: 'btn btn-primary', href: '/chat.html', text: 'מתחילים לתכנן ארון' }),
      ]));
      return;
    }
    if (inquiry.status === 'collecting_details') { location.replace('/chat.html'); return; }
    render(inquiry, catalog);
  } catch (err) {
    document.getElementById('loading').hidden = true;
    showError(pageAlert, err.status === 404 ? 'הפנייה לא נמצאה או שאין גישה אליה מדפדפן זה.' : err.message, init);
    pageAlert.hidden = false;
  }
}

function render(inquiry, catalog) {
  document.getElementById('content').hidden = false;
  document.getElementById('number').textContent = inquiry.number;
  document.getElementById('created').textContent = `נשלחה ${date(inquiry.submitted_at, true)}`;
  document.getElementById('status-chip').replaceChildren(chip(inquiry.status, inquiry.status_label));
  document.getElementById('spec-version').textContent = `— גרסה ${inquiry.spec.version}`;
  renderSpecGroups(document.getElementById('spec-groups'), inquiry.spec.spec, catalog, inquiry.spec.missing_fields);

  const idx = STEP_INDEX[inquiry.status] ?? 0;
  const stepper = document.getElementById('stepper');
  stepper.replaceChildren(...STEPS.map((s, i) => el('div', { class: `step${i < idx ? ' done' : ''}${i === idx ? ' current' : ''}` }, [
    el('span', { class: 'dot', text: i < idx ? '✓' : String(i + 1) }), s.label,
  ])));

  const box = document.getElementById('status-message');
  if (queryParam('submitted') === '1') toast('הפנייה נשלחה לנגר בהצלחה', 'success');
  if (inquiry.status === 'awaiting_carpenter') {
    box.replaceChildren(el('div', { class: 'alert alert-info' }, [
      el('span', { text: inquiry.requires_manual_review
        ? 'הפנייה ממתינה לבדיקה ידנית של הנגר (חסרים פרטים או שיש דרישה מיוחדת). נעדכן כאן כשתהיה הצעה.'
        : 'הפנייה ממתינה לבדיקת הנגר. נעדכן כאן כשתהיה הצעה.' }),
    ]));
  } else if (inquiry.status === 'change_requested') {
    box.replaceChildren(el('div', { class: 'alert alert-info' }, [el('span', { text: 'בקשת השינוי שלכם התקבלה. הנגר יעדכן את ההצעה.' }),
      el('a', { class: 'btn btn-sm btn-secondary', href: `/quote.html?inquiry=${inquiry.id}`, text: 'לצפייה בהצעה' })]));
  } else if (inquiry.has_quote) {
    box.replaceChildren(el('div', { class: 'alert alert-success' }, [
      el('span', { text: inquiry.status === 'accepted' ? 'ההצעה אושרה. הנגרייה תיצור קשר להמשך.' : 'יש הצעת מחיר מוכנה לצפייה!' }),
      el('a', { class: 'btn btn-sm btn-primary', href: `/quote.html?inquiry=${inquiry.id}`, text: 'לצפייה בהצעה' }),
    ]));
  } else if (inquiry.status === 'closed') {
    box.replaceChildren(el('div', { class: 'alert alert-info' }, [el('span', { text: 'הפנייה נסגרה.' })]));
  }

  const linkBtn = document.getElementById('link-btn');
  linkBtn.onclick = async () => {
    setBusy(linkBtn, true);
    try {
      const result = await post(`/api/inquiries/${inquiry.id}/access-link`);
      const url = `${location.origin}${result.path}`;
      document.getElementById('link-input').value = url;
      document.getElementById('link-expiry').textContent = `בתוקף עד ${date(result.expires_at)}. יצירת קישור נוסף אינה מבטלת את הקודם.`;
      document.getElementById('link-result').hidden = false;
    } catch (err) { toast(err.message, 'error'); } finally { setBusy(linkBtn, false); }
  };
  document.getElementById('copy-btn').onclick = async () => {
    try { await navigator.clipboard.writeText(document.getElementById('link-input').value); toast('הקישור הועתק', 'success'); }
    catch { document.getElementById('link-input').select(); toast('סמנו והעתיקו את הקישור ידנית'); }
  };
}

init();
