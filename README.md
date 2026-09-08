# ארון בהתאמה

אפליקציית MVP לנגרייה שמייצרת ארונות בהתאמה אישית. לקוח מתאר את הארון בשיחה בעברית,
סוכן AI מחלץ מפרט ושואל שאלות השלמה, קוד בצד השרת מחשב טיוטת מחיר, והנגר בודק, עורך,
מאשר ומפרסם הצעה ללקוח.

**עיקרון מחייב:** ה-AI אוסף דרישות ומנסח תשובות; המחיר מחושב אך ורק ב-`pricing_engine.py`.
המודל אינו קובע מחיר, הנחה, היתכנות ייצור או אישור של הנגר.

## מבנה

```
frontend/   HTML/CSS/JS + שרת Express שמגיש קבצים ומעביר /api ל-Backend (reverse proxy)
backend/    Flask API · routes / services / schemas / repositories / tests · migrations · seed
docs/       תיעוד: עיצוב (Stitch), תמחור, פריסה, משתני סביבה
```

| שכבה | טכנולוגיה |
|---|---|
| Backend | Python 3.12, Flask, Gunicorn, Pydantic, psycopg |
| Frontend | HTML, CSS, JavaScript (ES modules), Express (סטטי + proxy) |
| DB | Supabase PostgreSQL (סביבות מחוברות) / SQLite (דמו מקומי) |
| אימות נגר | Supabase Auth (JWT ES256 מאומת בשרת + טבלת `admin_users`) |
| AI | OpenAI Agents SDK (`openai-agents`), פלט מובנה Pydantic, כלים לקריאה בלבד |
| עיצוב | Google Stitch MCP → `docs/design-stitch.md` |
| פריסה | Railway (סביבות `dev` ו-`production`), GitHub (`dev` / `main`) |

## הפעלה מקומית (מצב דמו, ללא שירותים חיצוניים)

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; ב-Linux/mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                                # DEMO_MODE=true כברירת מחדל
python run_dev.py                                     # http://localhost:5000

# Frontend (טרמינל שני)
cd frontend
npm install
copy .env.example .env                                # BACKEND_URL=http://localhost:5000
npm start                                             # http://localhost:3000
```

במצב דמו: SQLite נוצר אוטומטית (`backend/data/demo.sqlite3`), נטענים קטלוג, מחירון דוגמה
ושש פניות בסטטוסים שונים (מחושבות דרך מנוע התמחור האמיתי), וסוכן ה-AI **מדומה ודטרמיניסטי**
(תשובותיו מסומנות ״[סימולציה]״). שמירה, תמחור, עריכת נגר וגרסאות עובדים באמת.

* אתר הלקוח: http://localhost:3000
* כניסת נגר: http://localhost:3000/admin/login.html → כפתור ״כניסת דמו כנגר״ (אין סיסמה).
  מעקף זה פעיל **רק** כאשר `DEMO_MODE=true` ו-`APP_ENV≠production`.

### בדיקות

```bash
cd backend && pytest        # 34 בדיקות: תמחור, גרסאות, הרשאות, בידוד, AI, תפוגה, כפילויות
```

## מעבר מדמו לשירותים אמיתיים

1. **Supabase:** צרו פרויקט (אחד לכל סביבה). קבלו `DATABASE_URL` (Session pooler, פורט 5432),
   `SUPABASE_URL`, מפתח `anon` ומפתח `service_role`.
2. **Backend `.env`:** `DEMO_MODE=false`, `APP_ENV`, `SESSION_SECRET` אקראי ארוך, `DATABASE_URL`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `OPENAI_MODEL`.
3. **Migrations:** `python scripts/run_migrations.py` (מבוקר, לא אוטומטי מכל worker).
4. **קטלוג ומחירון:** dev — `python scripts/seed_dev.py` (קטלוג + מחירון דוגמה; `--with-inquiries`
   לפניות לדוגמה). ייצור — `python scripts/seed_dev.py --catalog-only` בלבד; את המחירון האמיתי
   הנגר מגדיר במסך ״מחירון״ ומסמן ״אומת״. עד אז פרסום הצעות חסום בייצור.
5. **נגר מורשה:** ראו למטה.
6. **Frontend:** `BACKEND_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.

## יצירת משתמש נגר מורשה

אין הרשמה ציבורית. הסקריפט יוצר משתמש ב-Supabase Auth ומוסיף אותו ל-`admin_users`.
הסיסמה מוזנת אינטראקטיבית או דרך `ADMIN_PASSWORD` חד-פעמי — לא נשמרת בקוד או ב-seed.

```bash
cd backend
python scripts/create_admin_user.py --email carpenter@example.com --name "שם הנגר"
```

השרת מאשר בקשת ניהול רק אם ה-JWT תקף **וגם** `sub` קיים ופעיל ב-`admin_users`.

## תיעוד נוסף

* `docs/pricing-model.md` — נוסחאות, סדר חישוב, עיגול, הנחות ומע״מ.
* `docs/env-reference.md` — כל משתני הסביבה לכל שירות.
* `docs/deployment-railway.md` — סביבות Railway, חיבור לענפים, Supabase לכל סביבה, תהליך העבודה.
* `docs/design-stitch.md` — תוצרי Stitch, מזהים והחלטות עיצוב.

## סטטוסים

פנייה: `collecting_details → awaiting_carpenter → quote_available → change_requested / accepted → closed`
הצעה: `draft → published → accepted | superseded | expired | cancelled`
המעברים נאכפים ב-`services/status_machine.py`; פעולות משתמשות ב-`row_version` למניעת כפילויות.

## אבטחה בקצרה

* לקוח: session חתום (HttpOnly, SameSite=Lax, Secure בייצור) עם רשימת הפניות שלו; קישור אישי
  = טוקן אקראי חזק שרק ה-SHA-256 שלו נשמר, עם תפוגה וביטול; הטוקן מוחלף ל-session ומנוקה מהכתובת.
* CSRF: double-submit (`csrf_token` cookie + כותרת `X-CSRF-Token`); בדיקת Origin עם `FRONTEND_ORIGIN`.
* API ציבורי אינו מחזיר הערות פנימיות, טיוטות או פרטי מחירון.
* הגבלת אורך הודעה (2000), גודל בקשה (32KB) וקצב שימוש ב-AI (20 הודעות / 10 דק׳ לפנייה).
* המודל מקבל רק את המפרט וההיסטוריה — לא טוקנים ולא פרטי קשר; יש לו כלי קריאה לקטלוג בלבד.

## מגבלות ידועות

* הסוכן האמיתי פעיל רק כאשר מוגדר `OPENAI_API_KEY`; אחרת סוכן מדומה (מסומן).
* המחירון והמע״מ במחירון הדוגמה אינם מאומתים. שיעור המע״מ הוא הגדרה עסקית של הנגר.
* אין דוא״ל: ״פרסום״ פירושו זמינות בעמוד הלקוח בלבד.
* הגבלת הקצב היא בזיכרון (מתאימה לשירות יחיד).
