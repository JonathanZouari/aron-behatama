/**
 * שירות ה-Frontend: מגיש את הקבצים הסטטיים ומעביר כל בקשת /api ל-Backend
 * של אותה סביבה (BACKEND_URL). כך הדפדפן עובד מול origin אחד בלבד —
 * אין CORS, וה-cookies של הלקוח נשארים same-site.
 */
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3000);
const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:5000').replace(/\/$/, '');

const app = express();
app.disable('x-powered-by');

// בריאות השירות עצמו (לא של ה-Backend)
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'frontend', backend: BACKEND_URL }));

// תצורה ציבורית לדפדפן: רק ערכים שאינם סודיים (anon key מיועד לדפדפן לפי תכנון Supabase)
app.get('/config.js', (_req, res) => {
  const config = {
    supabaseUrl: process.env.SUPABASE_URL || '',
    supabaseAnonKey: process.env.SUPABASE_ANON_KEY || '',
    appEnv: process.env.APP_ENV || 'development',
  };
  res.type('application/javascript').set('Cache-Control', 'no-store');
  res.send(`window.APP_CONFIG = ${JSON.stringify(config)};`);
});

// reverse proxy: /api/* → BACKEND_URL/api/*
app.use(
  '/api',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    xfwd: true,
    pathFilter: () => true,
    pathRewrite: (p) => `/api${p}`,
    on: {
      error: (_err, _req, res) => {
        if (res && 'status' in res && !res.headersSent) {
          res.status(502).json({ success: false, error: 'שרת ה-API אינו זמין כרגע. נסו שוב בעוד רגע.' });
        }
      },
    },
  }),
);

app.use(
  express.static(path.join(__dirname, 'public'), {
    extensions: ['html'],
    setHeaders: (res) => {
      res.set('X-Content-Type-Options', 'nosniff');
      res.set('Referrer-Policy', 'no-referrer');
      res.set('X-Frame-Options', 'DENY');
    },
  }),
);

app.use((_req, res) => res.status(404).sendFile(path.join(__dirname, 'public', '404.html')));

app.listen(PORT, '0.0.0.0', () => {
  console.log(`frontend listening on 0.0.0.0:${PORT}, proxying /api → ${BACKEND_URL}`);
});
