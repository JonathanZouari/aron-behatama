/**
 * לקוח API יחיד לכל הממשק. הבקשות הולכות ל-/api באותו origin (ה-proxy מעביר ל-Backend).
 * - מוסיף כותרת CSRF מה-cookie לבקשות משנות-מצב.
 * - מוסיף Authorization לנגר כאשר יש token שמור.
 * - מנרמל שגיאות ל-ApiError עם הודעה בעברית מהשרת.
 */
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body || {};
  }
}

function readCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

const ADMIN_TOKEN_KEY = 'aron_admin_token';

export const adminToken = {
  get: () => {
    try { return sessionStorage.getItem(ADMIN_TOKEN_KEY); } catch { return null; }
  },
  set: (token) => {
    try { sessionStorage.setItem(ADMIN_TOKEN_KEY, token); } catch { /* אחסון חסום */ }
  },
  clear: () => {
    try { sessionStorage.removeItem(ADMIN_TOKEN_KEY); } catch { /* ignore */ }
  },
};

export async function api(method, path, body) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') {
    let csrf = readCookie('csrf_token');
    if (!csrf) {
      // בקשה ראשונה מגדירה את ה-cookie
      await fetch('/api/health', { credentials: 'same-origin' });
      csrf = readCookie('csrf_token');
    }
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  const token = adminToken.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('אין חיבור לשרת. בדקו את החיבור ונסו שוב.', 0);
  }
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok || (data && data.success === false)) {
    const message = (data && data.error) || `שגיאה (${response.status})`;
    throw new ApiError(message, response.status, data);
  }
  return data ? data.data : null;
}

export const get = (path) => api('GET', path);
export const post = (path, body) => api('POST', path, body ?? {});
export const patch = (path, body) => api('PATCH', path, body);
export const put = (path, body) => api('PUT', path, body);
