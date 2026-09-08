/** עמוד השיחה: צ'אט + כרטיס מפרט שמעדכנים את אותו מפרט שמור, עם מספרי גרסה. */
import { get, patch, post, ApiError } from './api.js';
import { el, esc, toast, setBusy, showError, FIELD_LABELS } from './ui.js';
import { SpecCard } from './spec-card.js';

const log = document.getElementById('chat-log');
const form = document.getElementById('chat-form');
const textarea = document.getElementById('chat-text');
const sendBtn = document.getElementById('send-btn');
const counter = document.getElementById('counter');
const quick = document.getElementById('quick-replies');
const saveIndicator = document.getElementById('save-indicator');
const pageAlert = document.getElementById('page-alert');

let inquiry = null;
let catalog = [];
let specCard = null;
let pendingPatch = {};
let saveTimer = null;

const QUICK_REPLIES = {
  body_material_id: (c) => c.filter((x) => x.kind === 'body_material').map((x) => `גוף ${x.name_he}`),
  front_material_id: (c) => c.filter((x) => x.kind === 'front_material').map((x) => `חזיתות ${x.name_he}`),
  finish_id: (c) => c.filter((x) => x.kind === 'finish').map((x) => `גימור ${x.name_he}`),
  depth_cm: () => ['עומק 60 ס״מ', 'עומק 50 ס״מ'],
  soft_close: () => ['עם טריקה שקטה', 'בלי טריקה שקטה'],
  delivery: () => ['עם הובלה', 'בלי הובלה'],
  installation: () => ['עם התקנה', 'בלי התקנה'],
};

async function init() {
  try {
    catalog = await get('/api/catalog');
    inquiry = await get('/api/inquiries/current');
    if (!inquiry || inquiry.status !== 'collecting_details') {
      inquiry = await post('/api/inquiries');
    }
    document.getElementById('inquiry-number').textContent = `פנייה ${inquiry.number}`;
    specCard = new SpecCard(document.getElementById('spec-form'), { catalog, onChange: onFormChange });
    renderSpec(inquiry.spec);
    await loadMessages();
  } catch (err) {
    showError(pageAlert, err.message || 'שגיאה בטעינה', init);
    pageAlert.hidden = false;
  }
}

async function loadMessages() {
  const messages = await get(`/api/inquiries/${inquiry.id}/messages`);
  log.replaceChildren();
  if (messages.length === 0) {
    addBubble('assistant', 'שלום! ספרו לי על הארון שאתם רוצים: מידות, כמה דלתות, איזה חומר וגימור. אפשר גם למלא ישירות בכרטיס המפרט.', {});
  }
  for (const m of messages) addBubble(m.role, m.content, { simulated: m.simulated });
  renderQuickReplies();
}

function addBubble(role, text, meta) {
  const bubble = el('div', { class: `bubble ${role}` }, [text]);
  if (meta && meta.simulated) bubble.append(el('span', { class: 'meta', text: 'סוכן מדומה (סימולציה)' }));
  log.append(bubble);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function renderSpec(specPayload) {
  inquiry.spec = specPayload;
  document.getElementById('spec-version').textContent = `— גרסה ${specPayload.version}`;
  specCard.render(specPayload.spec, specPayload.missing_fields);
  updateMeta(specPayload);
}

function updateMeta(specPayload) {
  const missing = specPayload.missing_fields || [];
  const summary = document.getElementById('missing-summary');
  summary.textContent = missing.length
    ? `שדות חסרים לתמחור: ${missing.map((f) => FIELD_LABELS[f] || f).join(', ')}. אפשר לשלוח גם כך — הפנייה תועבר לבדיקה ידנית.`
    : 'כל הפרטים הנחוצים לתמחור מולאו.';
  const badge = document.getElementById('manual-badge');
  const reasons = specPayload.manual_review_reasons || [];
  badge.hidden = !reasons.length;
  if (reasons.length) {
    badge.replaceChildren(el('div', { class: 'alert alert-warning' }, [
      el('span', {}, [el('strong', { text: 'נדרשת בדיקה ידנית של הנגר: ' }), reasons.join('; ')]),
    ]));
  }
  document.getElementById('ai-mode').textContent = '';
}

function renderQuickReplies() {
  quick.replaceChildren();
  const missing = inquiry.spec.missing_fields || [];
  const field = missing.find((f) => QUICK_REPLIES[f]);
  if (!field) return;
  for (const text of QUICK_REPLIES[field](catalog).slice(0, 4)) {
    quick.append(el('button', { type: 'button', text, onclick: () => { textarea.value = text; form.requestSubmit(); } }));
  }
}

/* ---- טופס → שמירה עם גרסה ---- */
function onFormChange(change) {
  pendingPatch = { ...pendingPatch, ...change };
  saveIndicator.textContent = 'שומר…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushPatch, 500);
}

async function flushPatch() {
  if (!Object.keys(pendingPatch).length) return;
  const body = { expected_version: inquiry.spec.version, patch: pendingPatch };
  pendingPatch = {};
  try {
    const saved = await patch(`/api/inquiries/${inquiry.id}/spec`, body);
    inquiry.spec = saved;
    document.getElementById('spec-version').textContent = `— גרסה ${saved.version}`;
    specCard.updateMissing(saved.missing_fields);
    updateMeta(saved);
    renderQuickReplies();
    saveIndicator.textContent = 'נשמר';
  } catch (err) {
    saveIndicator.textContent = 'לא נשמר';
    if (err instanceof ApiError && err.status === 409) {
      toast('המפרט עודכן במקביל — נטען מחדש', 'error');
      inquiry = await get(`/api/inquiries/${inquiry.id}`);
      renderSpec(inquiry.spec);
    } else {
      toast(err.message, 'error');
    }
  }
}

/* ---- שיחה ---- */
textarea.addEventListener('input', () => { counter.textContent = `${textarea.value.length}/2000`; });
textarea.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = textarea.value.trim();
  if (!text) return;
  await flushPatch();
  addBubble('user', text, {});
  textarea.value = ''; counter.textContent = '0/2000';
  setBusy(sendBtn, true);
  const typing = el('div', { class: 'bubble assistant typing', 'aria-label': 'העוזר מקליד' }, [el('span'), el('span'), el('span')]);
  log.append(typing); log.scrollTop = log.scrollHeight;
  try {
    const result = await post(`/api/inquiries/${inquiry.id}/chat`, { message: text, base_version: inquiry.spec.version });
    typing.remove();
    addBubble('assistant', result.reply, { simulated: result.simulated });
    renderSpec({
      version: result.spec_version, spec: result.spec, missing_fields: result.missing_fields,
      manual_review_reasons: result.manual_review_reasons, customer_confirmed: false,
    });
    renderQuickReplies();
  } catch (err) {
    typing.remove();
    if (err instanceof ApiError && err.status === 409) {
      toast('המפרט השתנה בטופס — טענו את הגרסה החדשה, שלחו שוב', 'error');
      inquiry = await get(`/api/inquiries/${inquiry.id}`);
      renderSpec(inquiry.spec);
      textarea.value = text;
    } else {
      const retry = el('button', { class: 'btn btn-sm btn-secondary', type: 'button', text: 'נסה שוב', onclick: () => { textarea.value = text; form.requestSubmit(); } });
      const msg = err.body && err.body.ai_unavailable
        ? 'העוזר אינו זמין כרגע. אפשר להמשיך למלא את המפרט בטופס משמאל.'
        : (err.message || 'שגיאה בשליחה');
      log.append(el('div', { class: 'alert alert-error', role: 'alert' }, [el('span', { text: msg }), retry]));
      log.scrollTop = log.scrollHeight;
    }
  } finally {
    setBusy(sendBtn, false);
  }
});

/* ---- מעבר נייד ---- */
for (const btn of document.querySelectorAll('.mobile-toggle button')) {
  btn.addEventListener('click', () => {
    document.getElementById('planner').dataset.view = btn.dataset.view;
    for (const b of document.querySelectorAll('.mobile-toggle button')) b.setAttribute('aria-pressed', String(b === btn));
  });
}

window.addEventListener('beforeunload', () => { if (Object.keys(pendingPatch).length) flushPatch(); });
init();
