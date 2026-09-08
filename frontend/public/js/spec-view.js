/** תצוגת מפרט לקריאה (קבוצות), משותפת לסיכום, מעקב והצעה. */
import { el, specFormatter, FIELD_LABELS } from './ui.js';

const GROUPS = [
  { title: 'מידות', fields: ['width_cm', 'height_cm', 'depth_cm'] },
  { title: 'חומרים וגימור', fields: ['body_material_id', 'front_material_id', 'finish_id', 'color'] },
  { title: 'חלוקה', fields: ['doors', 'internal_drawers', 'shelves', 'compartments'] },
  { title: 'שירותים', fields: ['soft_close', 'delivery', 'installation', 'city'] },
  { title: 'הערות ודרישות', fields: ['customer_notes', 'special_requirements'] },
];

/** מרנדר קבוצות מפרט לקריאה. משמש גם בעמודי מעקב/הצעה. */
export function renderSpecGroups(container, spec, catalog, missing = [], changes = {}) {
  const fmt = specFormatter(catalog);
  container.replaceChildren();
  for (const group of GROUPS) {
    const dl = el('dl', { class: 'kv' });
    for (const field of group.fields) {
      const text = fmt(field, spec[field]);
      const isMissing = missing.includes(field);
      if (text === null && !isMissing) continue;
      dl.append(el('dt', { text: FIELD_LABELS[field] }));
      const dd = el('dd');
      if (changes[field]) {
        const before = fmt(field, changes[field].before);
        dd.append(el('del', { text: before ?? 'לא צוין' }), ' → ', el('strong', { text: text ?? 'לא צוין' }), ' ', el('span', { class: 'chip warn', text: 'עודכן על ידי הנגר' }));
      } else if (text === null) {
        dd.append(el('span', { class: 'chip missing', text: 'חסר' }));
      } else {
        dd.textContent = text;
      }
      dl.append(dd);
    }
    if (dl.children.length) container.append(el('div', { class: 'group' }, [el('h4', { text: group.title }), dl]));
  }
}

