/** סיכום מפרט + פרטי קשר + אישור מפורש ושליחה לנגר. */
import { get, post, ApiError } from './api.js';
import { el, toast, setBusy, showError, FIELD_LABELS } from './ui.js';
import { renderSpecGroups } from './spec-view.js';

let inquiry = null;
const form = document.getElementById('contact-form');
const submitBtn = document.getElementById('submit-btn');
const pageAlert = document.getElementById('page-alert');

async function init() {
  try {
    const [catalog, current] = await Promise.all([get('/api/catalog'), get('/api/inquiries/current')]);
    inquiry = current;
    if (!inquiry) { location.replace('/chat.html'); return; }
    if (inquiry.status !== 'collecting_details') { location.replace(`/track.html?inquiry=${inquiry.id}`); return; }
    document.getElementById('spec-version').textContent = `— גרסה ${inquiry.spec.version}`;
    renderSpecGroups(document.getElementById('spec-groups'), inquiry.spec.spec, catalog, inquiry.spec.missing_fields);
    const missing = inquiry.spec.missing_fields || [];
    const alertBox = document.getElementById('missing-alert');
    if (missing.length) {
      alertBox.replaceChildren(el('div', { class: 'alert alert-warning' }, [
        el('span', {}, [el('strong', { text: 'שדות חסרים: ' }), missing.map((f) => FIELD_LABELS[f]).join(', '),
          '. אפשר לשלוח גם כך — הפנייה תועבר לבדיקה ידנית ולא יחושב עבורה מחיר אוטומטי מלא.']),
      ]));
    }
    const needsCity = inquiry.spec.spec.delivery || inquiry.spec.spec.installation;
    document.getElementById('city').required = Boolean(needsCity);
    if (inquiry.spec.spec.city) document.getElementById('city').value = inquiry.spec.spec.city;
    if (!needsCity) document.getElementById('city-note').textContent = '(אופציונלי)';
  } catch (err) {
    showError(pageAlert, err.message, init); pageAlert.hidden = false;
  }
}

function setErrors(errors) {
  for (const span of form.querySelectorAll('.error-text')) span.textContent = '';
  for (const input of form.querySelectorAll('input')) input.removeAttribute('aria-invalid');
  for (const [field, message] of Object.entries(errors || {})) {
    const span = form.querySelector(`[data-error-for="${field}"]`);
    const input = form.querySelector(`#${field}`);
    if (span) span.textContent = message;
    if (input) input.setAttribute('aria-invalid', 'true');
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  const errors = {};
  if (!data.full_name || data.full_name.trim().length < 2) errors.full_name = 'נא להזין שם מלא';
  if (!/^0\d{1,2}-?\d{7}$|^\+?\d{9,15}$/.test((data.phone || '').replace(/\s/g, ''))) errors.phone = 'נא להזין מספר טלפון תקין';
  if (document.getElementById('city').required && !data.city) errors.city = 'נדרשת עיר להובלה או להתקנה';
  if (!document.getElementById('confirm').checked) { errors.confirm = true; toast('יש לאשר את המפרט לפני השליחה', 'error'); }
  setErrors(errors);
  if (Object.keys(errors).length) return;

  setBusy(submitBtn, true);
  try {
    const result = await post(`/api/inquiries/${inquiry.id}/submit`, {
      spec_version: inquiry.spec.version, confirmed: true,
      full_name: data.full_name.trim(), phone: data.phone.trim(), email: data.email?.trim() || null, city: data.city?.trim() || null,
    });
    location.href = `/track.html?inquiry=${result.id}&submitted=1`;
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) setErrors(err.body.errors);
    if (err instanceof ApiError && err.status === 409) { toast('המפרט השתנה — נטען מחדש', 'error'); return init(); }
    toast(err.message, 'error');
  } finally {
    setBusy(submitBtn, false);
  }
});

init();
