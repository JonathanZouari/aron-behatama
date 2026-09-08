/**
 * התחברות הנגר.
 * - עם Supabase (SUPABASE_URL + ANON_KEY ב-/config.js): signInWithPassword דרך supabase-js מ-CDN,
 *   ו-access_token נשלח לשרת בכותרת Authorization. השרת מאמת JWT + admin_users.
 * - במצב דמו (ללא Supabase): טוקן דמו קבוע שהשרת מקבל רק כאשר DEMO_MODE=true ו-APP_ENV!=production.
 */
import { adminToken, get } from '../api.js';

const CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';
let client = null;

export function hasSupabase() {
  const c = window.APP_CONFIG || {};
  return Boolean(c.supabaseUrl && c.supabaseAnonKey);
}

async function supabase() {
  if (client) return client;
  const { createClient } = await import(CDN);
  const c = window.APP_CONFIG;
  client = createClient(c.supabaseUrl, c.supabaseAnonKey, { auth: { persistSession: true, autoRefreshToken: true } });
  return client;
}

export async function signIn(email, password) {
  const sb = await supabase();
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw new Error('פרטי ההתחברות שגויים');
  adminToken.set(data.session.access_token);
  sb.auth.onAuthStateChange((_event, session) => { if (session) adminToken.set(session.access_token); });
  return verify();
}

export function signInDemo() {
  adminToken.set('demo-carpenter-token');
  return verify();
}

/** מאמת מול השרת שהטוקן שייך לנגר מורשה. מחזיר פרטי נגר או זורק. */
export async function verify() {
  try {
    return await get('/api/admin/me');
  } catch (err) {
    if (err.status === 401 || err.status === 403) adminToken.clear();
    throw new Error(err.status === 403 ? 'המשתמש מחובר אך אינו נגר מורשה' : 'פרטי ההתחברות שגויים או שאין הרשאת נגר');
  }
}

export async function refreshTokenIfPossible() {
  if (!hasSupabase()) return;
  const sb = await supabase();
  const { data } = await sb.auth.getSession();
  if (data.session) adminToken.set(data.session.access_token);
}

export async function signOut() {
  adminToken.clear();
  if (hasSupabase()) { try { (await supabase()).auth.signOut(); } catch { /* ignore */ } }
  location.href = '/admin/login.html';
}

/** שומר על התחברות בכל עמוד ניהול; מפנה ל-login אם אין הרשאה. */
export async function requireCarpenter() {
  await refreshTokenIfPossible();
  if (!adminToken.get()) { location.replace('/admin/login.html'); return null; }
  try { return await get('/api/admin/me'); } catch { adminToken.clear(); location.replace('/admin/login.html'); return null; }
}
