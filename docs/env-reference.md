# משתני סביבה

## Backend (`/backend`)

| משתנה | חובה | תיאור |
|---|---|---|
| `APP_ENV` | כן | `development` או `production`. בייצור: דמו חסום, cookies Secure, HSTS, פרסום הצעות רק עם מחירון מאומת. |
| `PORT` | Railway מגדיר | פורט ההאזנה. ב-Railway מוגדר `8080` כדי שה-Frontend יפנה ל-`backend.railway.internal:8080`. |
| `DEMO_MODE` | כן | `true` = SQLite + סוכן מדומה + נגר דמו. **אסור** עם `APP_ENV=production` (ההפעלה נכשלת). |
| `SQLITE_PATH` | בדמו | נתיב קובץ SQLite (ברירת מחדל `data/demo.sqlite3`; `:memory:` לבדיקות). |
| `SESSION_SECRET` | כן | סוד חתימת cookie ה-session של הלקוח. ≥32 תווים בייצור. |
| `FRONTEND_ORIGIN` | מומלץ | origin של ה-Frontend לבדיקת Origin/Referer בבקשות משנות-מצב. |
| `DATABASE_URL` | כשלא דמו | חיבור Postgres של Supabase (Session pooler, פורט 5432). |
| `SUPABASE_URL` | כשלא דמו | `https://<ref>.supabase.co` — לאימות JWT דרך JWKS. |
| `SUPABASE_SERVICE_ROLE_KEY` | לסקריפטים | נדרש ל-`scripts/create_admin_user.py` (Admin API). השרת עצמו אינו משתמש בו בזמן ריצה. |
| `SUPABASE_JWT_SECRET` | לא | אם מוגדר — אימות HS256 עם הסוד במקום JWKS (פרויקטים ישנים). |
| `OPENAI_API_KEY` | לסוכן אמיתי | ללא מפתח, השרת משתמש בסוכן המדומה ומתעד אזהרה. |
| `OPENAI_MODEL` | לא | ברירת מחדל `gpt-5-mini`. |
| `AI_ENABLED` | לא | `false` = סוכן מדומה גם כשיש מפתח. |
| `FORCE_SECURE_COOKIES` | לא | `true` כדי לאלץ cookies Secure מחוץ לייצור (HTTPS). |

## Frontend (`/frontend`)

| משתנה | חובה | תיאור |
|---|---|---|
| `PORT` | Railway מגדיר | פורט ההאזנה. |
| `BACKEND_URL` | כן | יעד ה-proxy של `/api`. מקומי `http://localhost:5000`; Railway `http://backend.railway.internal:8080`. |
| `SUPABASE_URL` | להתחברות נגר | מוגש לדפדפן דרך `/config.js`. ריק = כפתור ״כניסת דמו״. |
| `SUPABASE_ANON_KEY` | להתחברות נגר | מפתח anon (ציבורי לפי תכנון Supabase). |
| `APP_ENV` | לא | לתצוגת תגית סביבה. |

## ערכים בפועל ב-Railway

הוגדרו לכל שירות ולכל סביבה (dev / production) בנפרד. `OPENAI_API_KEY` **לא** הוגדר —
יש להוסיף אותו בלוח Railway (backend, בכל סביבה) כדי להפעיל את סוכן ה-OpenAI במקום המדומה.
