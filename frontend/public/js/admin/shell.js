/** מעטפת עמודי הניהול: פס ניווט, אימות, פרטי נגר ותגית סביבה. */
import { el } from '../ui.js';
import { requireCarpenter, signOut } from './auth.js';

const NAV = [
  { href: '/admin/dashboard.html', label: 'לוח בקרה ופניות' },
  { href: '/admin/customers.html', label: 'לקוחות' },
  { href: '/admin/pricebook.html', label: 'מחירון' },
  { href: '/', label: 'אתר הלקוחות' },
];

export async function mountShell() {
  const me = await requireCarpenter();
  if (!me) return null;
  const rail = document.getElementById('rail');
  const current = location.pathname;
  rail.replaceChildren(
    el('a', { class: 'brand', href: '/admin/dashboard.html' }, [el('span', { class: 'brand-mark', 'aria-hidden': 'true', text: 'א' }), 'ארון בהתאמה']),
    ...NAV.map((n) => el('a', { href: n.href, text: n.label, 'aria-current': current === n.href ? 'page' : null })),
    el('div', { class: 'rail-footer' }, [
      el('span', { text: me.display_name }),
      el('span', { class: 'muted', text: me.email, style: 'color:#d9c8b3;font-size:0.75rem;direction:ltr;text-align:end' }),
      el('span', { class: 'env-badge', text: me.demo_mode ? 'מצב דמו' : (me.app_env === 'production' ? 'ייצור' : 'סביבת פיתוח') }),
      el('a', { href: '#', text: 'יציאה', onclick: (e) => { e.preventDefault(); signOut(); } }),
    ]),
  );
  return me;
}
