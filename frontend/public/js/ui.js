/** עזרי ממשק: escaping (אין הזרקת HTML מטקסט משתמש/AI), toast, פורמט, תוויות. */

export function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function toast(message, kind = 'info') {
  let host = document.querySelector('.toast-host');
  if (!host) { host = el('div', { class: 'toast-host', role: 'status', 'aria-live': 'polite' }); document.body.append(host); }
  const item = el('div', { class: `toast ${kind}`, text: message });
  host.append(item);
  setTimeout(() => item.remove(), 4500);
}

export function money(value) {
  if (value === null || value === undefined || value === '') return '—';
  const num = Number(value);
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 2 }).format(num);
}

export function percent(rate) {
  return `${(Number(rate) * 100).toLocaleString('he-IL', { maximumFractionDigits: 2 })}%`;
}

export function date(iso, withTime = false) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('he-IL', withTime
    ? { dateStyle: 'short', timeStyle: 'short' }
    : { dateStyle: 'medium' });
}

export function setBusy(button, busy) {
  if (!button) return;
  button.toggleAttribute('disabled', busy);
  if (busy) button.setAttribute('aria-busy', 'true'); else button.removeAttribute('aria-busy');
}

export const STATUS_LABELS = {
  collecting_details: 'איסוף פרטים', awaiting_carpenter: 'ממתינה לנגר', quote_available: 'הצעה זמינה',
  change_requested: 'בקשת שינוי', accepted: 'אושרה', closed: 'סגורה',
  draft: 'טיוטה', published: 'פורסמה', superseded: 'הוחלפה', expired: 'פג תוקף', cancelled: 'בוטלה',
};

export function chip(status, label) {
  return el('span', { class: 'chip', 'data-status': status, text: label || STATUS_LABELS[status] || status });
}

export const FIELD_LABELS = {
  width_cm: 'רוחב (ס״מ)', height_cm: 'גובה (ס״מ)', depth_cm: 'עומק (ס״מ)',
  body_material_id: 'חומר גוף', front_material_id: 'חומר חזיתות', finish_id: 'גימור', color: 'צבע',
  doors: 'דלתות', internal_drawers: 'מגירות פנימיות', shelves: 'מדפים', compartments: 'תאים אנכיים',
  soft_close: 'טריקה שקטה', delivery: 'הובלה', installation: 'התקנה', city: 'עיר',
  customer_notes: 'הערות', special_requirements: 'דרישות מיוחדות',
};

export const SPEC_FIELD_ORDER = Object.keys(FIELD_LABELS);

/** מחזיר פונקציה שממירה ערך מפרט לטקסט קריא לפי הקטלוג. */
export function specFormatter(catalog) {
  const names = Object.fromEntries((catalog || []).map((c) => [c.code, c.name_he]));
  return (field, value) => {
    if (value === null || value === undefined || value === '') return null;
    if (typeof value === 'boolean') return value ? 'כן' : 'לא';
    if (field.endsWith('_id')) return names[value] || value;
    if (field.endsWith('_cm')) return `${value} ס״מ`;
    return String(value);
  };
}

export function queryParam(name) {
  return new URLSearchParams(location.search).get(name);
}

export function showError(container, message, retry) {
  container.replaceChildren(el('div', { class: 'alert alert-error', role: 'alert' }, [
    el('span', { text: message }),
    retry ? el('button', { class: 'btn btn-sm btn-secondary', type: 'button', text: 'נסה שוב', onclick: retry }) : null,
  ]));
}

/**
 * דיאלוג אישור/סיבה בתוך העמוד (במקום confirm/prompt של הדפדפן).
 * מחזיר Promise: null אם בוטל, אחרת מחרוזת הסיבה ('' אם לא נדרשה).
 */
export function askDialog({ title, message, withReason = false, confirmLabel = 'אישור', danger = false }) {
  return new Promise((resolve) => {
    const input = withReason ? el('textarea', { id: 'dlg-reason', maxlength: 500, rows: 3, required: true }) : null;
    const dialog = el('dialog', { class: 'card', style: 'max-width:440px;width:100%' }, [
      el('h2', { text: title, style: 'font-size:1.15rem' }),
      message ? el('p', { class: 'muted small', text: message }) : null,
      input ? el('div', { class: 'field' }, [el('label', { for: 'dlg-reason', text: 'סיבה (תישמר בהיסטוריה)' }), input]) : null,
      el('div', { class: 'row', style: 'margin-top:0.75rem' }, [
        el('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, type: 'button', text: confirmLabel, onclick: () => {
          if (input && !input.value.trim()) { input.focus(); return; }
          dialog.close(); resolve(input ? input.value.trim() : '');
        } }),
        el('button', { class: 'btn btn-ghost', type: 'button', text: 'ביטול', onclick: () => { dialog.close(); resolve(null); } }),
      ]),
    ]);
    dialog.addEventListener('close', () => { dialog.remove(); });
    dialog.addEventListener('cancel', () => resolve(null));
    document.body.append(dialog);
    dialog.showModal();
  });
}
