# תוכנית יישום: ״ארון בהתאמה״ (MVP מלא)

## Context

הלקוח ביקש אפליקציית MVP עובדת לנגרייה: לקוח מתאר ארון בצ׳אט בעברית, סוכן AI מחלץ מפרט, מנוע תמחור דטרמיניסטי בשרת מחשב טיוטה, והנגר עורך/מאשר/מפרסם הצעה ב־Dashboard. הפרויקט לימודי, לכן הקוד חייב להיות קריא, מופרד לשכבות (routes / services / schemas / repositories / tests) ומאובטח.
התיקייה `C:\Users\User\Desktop\The Nagaria` ריקה, אין git. הדרישות המפורטות של המשתמש (17 סעיפים) הן ה־spec; המסמך הזה הוא תוכנית הביצוע.

### מצב הכלים שנבדק (read-only)
| כלי | מצב |
|---|---|
| Python 3.13.5, Node 22.17.1, git 2.54 | זמינים |
| GitHub CLI | מחובר כ־JonathanZouari (scopes: repo, workflow) |
| Stitch MCP | מחובר, 38 פרויקטים קיימים, אין פרויקט קשור → ייווצר פרויקט חדש |
| Supabase CLI 2.84 | מחובר; ארגון קיים אחד (`Policy Research Copilot`). המשתמש אישר ליצור **ארגון חדש** + פרויקטים חדשים |
| Supabase MCP | דורש OAuth — לא נדרש, עובדים עם ה־CLI |
| Railway CLI 5.30 | מותקן, **לא מחובר** — המשתמש יריץ `! railway login` |
| OpenAI key | המשתמש יספק; יוזרק כמשתנה סביבה בלבד |

### החלטות שהמשתמש אישר
- מאגר GitHub: `JonathanZouari/aron-behatama`, **ציבורי**, ענפים `dev` ו־`main`.
- Supabase: ארגון חדש (`aron-behatama`) ובתוכו שני פרויקטים: `aron-behatama-dev`, `aron-behatama-prod` (region `eu-central-1`). סיסמאות DB ייווצרו אקראית ויישמרו רק במשתני סביבה מקומיים/Railway, לא ב־Git.
- Railway: פרויקט אחד, סביבות `dev` + `production`, 4 שירותים לפי הטבלה בדרישות.

### הנחות שגרתיות (ממשיכים בלי לשאול)
- מע״מ ברירת מחדל בהגדרות: 18% מסומן ״ערך לדוגמה — יש לאמת מול רו״ח״, ניתן לעריכה במסך המחירון. **לא** מוצג כשיעור חוקי מאומת.
- מודל OpenAI דרך `OPENAI_MODEL` (ברירת מחדל `gpt-5-mini`, לפי התיעוד הרשמי שייבדק בזמן המימוש).
- Frontend proxy: שרת Node קטן (`express` + `http-proxy-middleware`) — פשוט, מגיש סטטי, מעביר `/api` ל־`BACKEND_URL`. הדפדפן עובד מול `/api` באותו origin.
- אזורי הובלה: 4 אזורים לדוגמה (מרכז, שרון/שפלה, צפון, דרום) + ״אחר״ → תמחור ידני.
- קישור גישה ללקוח: `/track?token=…` → השרת מחליף ל־cookie session (HttpOnly, Secure בפריסה, SameSite=Lax) ומנקה את הטוקן מה־URL ב־redirect.
- CSRF: כותרת `X-CSRF-Token` שנשמרת ב־cookie נפרד (double-submit) לפעולות state-changing של לקוח ונגר; נגר מזוהה גם ב־Bearer JWT של Supabase.
- SQLite לדמו דרך `sqlite3` סטנדרטי + אותו סכמת SQL (עם התאמות טיפוסים); Supabase דרך `supabase-py` עם service role בשרת בלבד + בדיקות הרשאה מפורשות בכל endpoint.

## מבנה המאגר

```
aron-behatama/
├── README.md                     (עברית: הפעלה, נגר מורשה, תמחור, דמו→אמיתי, env, Railway, Stitch)
├── docs/
│   ├── design-stitch.md          (מזהי פרויקט/מסכים ב־Stitch, החלטות עיצוב)
│   ├── pricing-model.md
│   ├── deployment-railway.md
│   └── env-reference.md
├── .gitignore
├── frontend/
│   ├── package.json              (build: no-op/echo, start: node server.js)
│   ├── server.js                 (express static + proxy /api → BACKEND_URL, PORT, 0.0.0.0, /health)
│   ├── .env.example
│   ├── railway.json
│   └── public/
│       ├── index.html, chat.html, summary.html, track.html, quote.html
│       ├── admin/login.html, dashboard.html, inquiry.html, pricebook.html, customers.html
│       ├── css/tokens.css, base.css, components.css, customer.css, admin.css
│       └── js/api.js, ui.js (escape/toast/loading), spec-card.js, chat.js, summary.js,
│              track.js, quote.js, admin/auth.js, dashboard.js, inquiry.js, pricebook.js, customers.js
└── backend/
    ├── requirements.txt  (flask, gunicorn, pydantic, openai-agents, supabase, PyJWT[crypto], python-dotenv, pytest)
    ├── Procfile / railway.json (start: gunicorn -b 0.0.0.0:$PORT "app:create_app()")
    ├── .env.example
    ├── app/
    │   ├── __init__.py            create_app, config, blueprints, security headers
    │   ├── config.py              APP_ENV, DEMO_MODE, guards (DEMO+production → refuse)
    │   ├── routes/  health.py, public_inquiries.py, public_chat.py, public_quotes.py,
    │   │            admin_auth.py, admin_inquiries.py, admin_quotes.py, admin_pricebook.py, admin_customers.py
    │   ├── schemas/ wardrobe_spec.py, agent_output.py, pricing.py, quote.py, api.py (Pydantic)
    │   ├── services/ spec_service.py, pricing_engine.py, quote_service.py, status_machine.py,
    │   │             access_tokens.py, csrf.py, auth_admin.py (JWT verify), rate_limit.py,
    │   │             ai/agent.py (OpenAI Agents SDK), ai/mock_agent.py, ai/tools.py (catalog read-only), ai/units.py
    │   ├── repositories/ base.py (Protocol), sqlite_repo.py, supabase_repo.py, factory.py
    │   └── seed/ catalog.py, pricebook_dev.py, demo_inquiries.py
    ├── migrations/ 0001_init.sql (Postgres) + sqlite/0001_init.sql, run_migrations.py
    ├── scripts/ create_admin_user.py, seed_dev.py
    └── tests/ (pytest) — לפי סעיף 16
```

## שלבי ביצוע

### שלב 0 — תשתית מאגר
1. `git init`, ענף `main`, ואז `dev`. `.gitignore` (env, sqlite, node_modules, __pycache__).
2. `gh repo create JonathanZouari/aron-behatama --public`, push של שני הענפים.
3. שמירת `docs/superpowers/specs/2026-09-08-aron-behatama-design.md` (תמצית הדרישות + החלטות מעלה).

### שלב 1 — עיצוב ב־Stitch
1. `create_project` ״ארון בהתאמה״, `create_design_system` (עץ/בהיר/ירוק כהה, RTL, Heebo/Assistant).
2. `generate_screen_from_text` ל־10 המסכים (עברית, RTL, נייד+מחשב, מצבי טעינה/שגיאה/ריק).
3. `get_screen` לשליפת HTML/CSS → בסיס ל־`frontend/public`. תיעוד ב־`docs/design-stitch.md` עם מזהים.
   אם קריאה נכשלת — ממשיכים ומתעדים בדיוק מה חסר.

### שלב 2 — סכמה, migrations, repositories
- טבלאות לפי סעיף 12 (UUID, FK, אינדקסים, timestamptz UTC, `numeric(12,2)`, CHECK constraints לסטטוסים ולמידות, `spec_snapshot jsonb` ו־`pricing_snapshot jsonb` ב־`quotes`, `token_hash` ב־`customer_access_tokens`, `inquiry_events` עם `actor_type/actor_id`).
- `ALTER TABLE … ENABLE ROW LEVEL SECURITY` על כולן, ללא policies ציבוריות.
- Repository Protocol אחד; SQLite ו־Supabase מיישמים אותו. גרסאות אופטימיות: `spec_version`, `quote.version`, `UPDATE … WHERE version = ?`.

### שלב 3 — מנוע תמחור (TDD)
`pricing_engine.py`: Decimal, `ROUND_HALF_UP` לאגורות בסוף כל סעיף, סדר 13 השלבים מהדרישות, נוסחאות שטח מהמודל. פלט: `PricingResult{items[], subtotal, vat, total, manual_required[], pricebook_version}`. מידע חסר / אזור ללא מחיר / דרישה מיוחדת → `manual_required` ואין `total`. התאמה ידנית מחייבת `reason`. סה״כ שלילי → שגיאה.

### שלב 4 — תהליך לקוח + סוכן AI
- `POST /api/inquiries` (יוצר פנייה + conversation, מחזיר session cookie), `PATCH /api/inquiries/me/spec` (טופס, עם `expected_version`), `POST /api/chat/messages` (AI; שרת מאמת פלט Pydantic, ממזג patch רק אם `base_version` תואם; אחרת מחזיר 409 והלקוח מנסה שוב), `POST /api/inquiries/me/submit` (שם+טלפון, אישור מפורש, idempotent), `GET /api/inquiries/me`, `POST /api/access-links` (טוקן `secrets.token_urlsafe(32)`, hash sha256, תפוגה 30 יום, ביטול).
- סוכן: OpenAI Agents SDK, `output_type=AgentOutput`, כלים read-only בלבד (`get_catalog`, `explain_option`). המרת יחידות בקוד (`units.py`) + ולידציה. `mock_agent.py` דטרמיניסטי (regex לחילוץ מידות/חומרים), מסומן `simulated: true` בתשובה.
- הגבלות: אורך הודעה 2,000 תווים, גוף בקשה 32KB, rate limit בזיכרון לפי session (למשל 20 הודעות AI / 10 דק׳).
- הלקוח לא מקבל בשום endpoint ציבורי: `internal_notes`, טיוטות (`status='draft'`), מחירי עלות.

### שלב 5 — Dashboard נגר והרשאות
- אימות: הדפדפן משתמש ב־Supabase JS (CDN) ל־`signInWithPassword`; שולח `Authorization: Bearer <access_token>`. השרת מאמת JWT (JWKS / `SUPABASE_JWT_SECRET` לפי התיעוד העדכני) **וגם** בודק `admin_users.user_id` — רק אז `carpenter`.
- `scripts/create_admin_user.py`: יוצר משתמש דרך Admin API (service role) עם סיסמה שמוזנת אינטראקטיבית/ENV חד-פעמי, ומוסיף ל־`admin_users`. אין הרשמה ציבורית.
- דמו: `DEMO_MODE=true` + `APP_ENV!=production` → נגר דמו ללא Supabase; אם `APP_ENV=production` ההפעלה נכשלת עם שגיאה ברורה.
- Endpoints: סטטיסטיקות, רשימת פניות (חיפוש/סינון), פרטי פנייה (כולל שיחה, אירועים, גרסאות), עריכת מפרט (מבטלת אישור לקוח ומסמנת draft כ־stale), חישוב מחדש, סעיפים ידניים, יצירת גרסת הצעה, פרסום, ביטול, סגירה, מחירון (CRUD, השבתה, הגדרות פחת/מע״מ/תוקף — יצירת גרסת מחירון חדשה בשמירה), לקוחות + קישור פנייה ללקוח קיים.

### שלב 6 — הצעות, גרסאות, אישורים
`status_machine.py` מגדיר מעברים מותרים לפנייה ולהצעה ואוכף בשרת. פרסום: snapshot מפרט+תמחור, `published_at`, `expires_at` מהגדרות; גרסה קודמת → `superseded`. אישור לקוח: `POST /api/quotes/{id}/accept` עם `version`; בודק תפוגה ברגע הפעולה, סטטוס `published`, שאין `change_requested` פתוח; idempotent. בקשת שינוי → פנייה `change_requested`, ההצעה לא ניתנת לאישור עד טיפול. הצגת diff מפרט (מה שנשלח מול מה שפורסם). בייצור: חסימת פרסום עד שקיים מחירון פעיל עם `vat_rate` ותוקף מוגדרים ו־`confirmed_by_carpenter=true`.

### שלב 7 — בדיקות
pytest על SQLite in-memory + mock agent: כל הרשימה בסעיף 16 (תמחור/פחת/עיגול/מע״מ, מניעת חיוב כפול, חוסר מידע→ידני, פלט AI פסול, המרת יחידות, גרסאות מול AI ישן, הרשאות/בידוד, אי-חשיפת פנימי, תפוגה/גרסאות, אישור גרסה נכונה, כפילויות, מחיר היסטורי). בדיקת flow מלא אחת end-to-end דרך Flask test client.
בדיקת דפדפן (Claude in Chrome) מול השרת המקומי בדמו ואז מול dev ב־Railway: תהליך מלא, בקשת שינוי, פנייה חסרה, נייד/מחשב.

### שלב 8 — Supabase, Railway, פריסה
1. `supabase orgs create` → `supabase projects create aron-behatama-dev / -prod --region eu-central-1` (סיסמאות אקראיות, לא ב־Git). הרצת `0001_init.sql` דרך `supabase db push`/`psql` לכל פרויקט. יצירת נגר מורשה בכל סביבה. seed רק ב־dev.
2. Railway (אחרי `railway login` של המשתמש; ישתמש בסקיל `railway-provision`/`railway:new`): פרויקט `aron-behatama`, סביבות `dev`/`production`, 4 שירותים מהרפו עם Root Directory וענף מפורש, watch paths (`frontend/**`, `backend/**`), auto-deploy, `/health` כ־healthcheck, משתנים: backend — `APP_ENV, PORT, DEMO_MODE=false, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET/ANON, OPENAI_API_KEY, OPENAI_MODEL, SESSION_SECRET`; frontend — `PORT, BACKEND_URL, SUPABASE_URL, SUPABASE_ANON_KEY` (מוגש ל־login בלבד). Auth redirect URLs לפי דומייני Railway בפועל.
3. אימות: curl ל־`/health` ב־4 שירותים, בדיקת proxy של כל frontend מול ה־backend הנכון, login נגר בכל סביבה, דחיפה ל־`dev` פורסת רק dev. הצגת כתובות. אם משהו לא אומת — נאמר במפורש.

## דרישות מהמשתמש בזמן הביצוע
- להריץ `! railway login` (לפני שלב 8).
- לספק `OPENAI_API_KEY` (יוזרק ל־Railway בלבד; מקומית יוכנס ל־`.env` שאינו ב־Git).
- ליבחר סיסמת נגר בזמן הרצת `create_admin_user.py` לכל סביבה (או שאייצר אקראית ואמסור פעם אחת).

## מגבלות/סיכונים ידועים
- תוכנית Supabase חינמית מגבילה מספר פרויקטים פעילים לארגון; אם יצירת הפרויקט השני תיחסם — לא אשדרג חבילה, אדווח.
- Railway עשוי לדרוש חיבור GitHub App לחשבון בפעם הראשונה בדפדפן.
- Stitch מייצר HTML לא-RTL לעיתים; יבוצע תיקון ידני ויתועד.
