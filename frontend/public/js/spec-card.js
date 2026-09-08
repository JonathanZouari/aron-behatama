/**
 * כרטיס מפרט: טופס עריכה של מפרט הארון, משותף ללקוח ולנגר.
 * מקבל קטלוג + מפרט, מסמן שדות חסרים, ומחזיר patch של השדות ששונו.
 */
import { el, FIELD_LABELS } from './ui.js';

const NUMBER_FIELDS = ['width_cm', 'height_cm', 'depth_cm', 'doors', 'internal_drawers', 'shelves', 'compartments'];
const BOOL_FIELDS = ['soft_close', 'delivery', 'installation'];
const CATALOG_FIELDS = { body_material_id: 'body_material', front_material_id: 'front_material', finish_id: 'finish' };
const SECTIONS = [
  { title: 'מידות', fields: ['width_cm', 'height_cm', 'depth_cm'] },
  { title: 'חומרים וגימור', fields: ['body_material_id', 'front_material_id', 'finish_id', 'color'] },
  { title: 'חלוקה פנימית', fields: ['doors', 'internal_drawers', 'shelves', 'compartments'] },
  { title: 'תוספות ושירותים', fields: ['soft_close', 'delivery', 'installation', 'city'] },
  { title: 'הערות', fields: ['customer_notes', 'special_requirements'] },
];

export class SpecCard {
  /** @param {HTMLElement} root  @param {{catalog: Array, onChange?: Function, readonly?: boolean}} opts */
  constructor(root, opts) {
    this.root = root;
    this.catalog = opts.catalog || [];
    this.onChange = opts.onChange || (() => {});
    this.readonly = Boolean(opts.readonly);
    this.spec = {};
    this.missing = [];
    this.inputs = {};
    this.dirty = {};
  }

  render(spec, missing = []) {
    this.spec = { ...spec };
    this.missing = missing;
    this.dirty = {};
    this.root.replaceChildren();
    for (const section of SECTIONS) {
      const grid = el('div', { class: section.fields.some((f) => f.endsWith('notes') || f.endsWith('requirements')) ? 'stack' : 'form-grid' });
      for (const field of section.fields) grid.append(this._field(field));
      this.root.append(el('div', { class: 'spec-section' }, [el('h4', { text: section.title }), grid]));
    }
  }

  _field(field) {
    const value = this.spec[field];
    const isMissing = this.missing.includes(field);
    const id = `spec-${field}`;
    let control;
    if (BOOL_FIELDS.includes(field)) {
      control = el('select', { id, name: field }, [
        el('option', { value: '', text: isMissing ? 'לא צוין' : '—' }),
        el('option', { value: 'true', text: 'כן' }),
        el('option', { value: 'false', text: 'לא' }),
      ]);
      control.value = value === null || value === undefined ? '' : String(value);
    } else if (CATALOG_FIELDS[field]) {
      const options = this.catalog.filter((c) => c.kind === CATALOG_FIELDS[field]);
      control = el('select', { id, name: field }, [
        el('option', { value: '', text: 'לא צוין' }),
        ...options.map((o) => el('option', { value: o.code, text: o.name_he })),
      ]);
      control.value = value ?? '';
    } else if (NUMBER_FIELDS.includes(field)) {
      control = el('input', { id, name: field, type: 'number', inputmode: 'numeric', min: field === 'compartments' ? 1 : 0, value: value ?? '', placeholder: isMissing ? 'חסר' : '' });
    } else if (field === 'customer_notes' || field === 'special_requirements') {
      control = el('textarea', { id, name: field, rows: 2, maxlength: 2000 });
      control.value = value ?? '';
    } else {
      control = el('input', { id, name: field, type: 'text', maxlength: 80, value: value ?? '' });
    }
    if (this.readonly) control.setAttribute('disabled', '');
    control.addEventListener('change', () => this._changed(field, control));
    control.addEventListener('input', () => this._debouncedChange(field, control));
    const labelRow = el('label', { for: id }, [FIELD_LABELS[field]]);
    if (isMissing) labelRow.append(' ', el('span', { class: 'chip missing', text: 'חסר' }));
    return el('div', { class: `field${isMissing ? ' missing' : ''}` }, [labelRow, control]);
  }

  _debouncedChange(field, control) {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._changed(field, control), 700);
  }

  _changed(field, control) {
    clearTimeout(this._timer);
    const raw = control.value;
    let parsed;
    if (raw === '') parsed = null;
    else if (BOOL_FIELDS.includes(field)) parsed = raw === 'true';
    else if (NUMBER_FIELDS.includes(field)) parsed = Number.parseInt(raw, 10);
    else parsed = raw.trim() || null;
    if (Number.isNaN(parsed)) return;
    if (parsed === (this.spec[field] ?? null)) return;
    this.spec[field] = parsed;
    this.dirty[field] = parsed;
    this.onChange({ [field]: parsed });
  }

  /** מסמן/מבטל סימון "חסר" בלי לבנות מחדש את הטופס (כדי לא לאבד מיקוד). */
  updateMissing(missing) {
    this.missing = missing;
    for (const wrapper of this.root.querySelectorAll('.field')) {
      const control = wrapper.querySelector('input, select, textarea');
      const field = control?.name;
      const isMissing = missing.includes(field);
      wrapper.classList.toggle('missing', isMissing);
      const chip = wrapper.querySelector('.chip.missing');
      if (isMissing && !chip) wrapper.querySelector('label').append(' ', el('span', { class: 'chip missing', text: 'חסר' }));
      if (!isMissing && chip) chip.remove();
    }
  }
}
