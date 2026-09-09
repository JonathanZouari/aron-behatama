# פריסה — Railway, Supabase ותהליך העבודה

## מבנה הפריסה

פרויקט Railway אחד: **aron-behatama** (`bea0652d-870b-4c84-89ba-c0424c3712bd`).

| סביבה | שירות | Root Directory | ענף GitHub | Watch paths | כתובת |
|---|---|---|---|---|---|
| `dev` | `frontend` | `/frontend` | `dev` | `/frontend/**` | https://frontend-dev-84d3.up.railway.app |
| `dev` | `backend` | `/backend` | `dev` | `/backend/**` | https://backend-dev-efdc.up.railway.app |
| `production` | `frontend` | `/frontend` | `main` | `/frontend/**` | https://frontend-production-9007.up.railway.app |
| `production` | `backend` | `/backend` | `main` | `/backend/**` | https://backend-production-68d39.up.railway.app |

* מאגר: https://github.com/JonathanZouari/aron-behatama (ציבורי).
* פריסה אוטומטית: דחיפה ל-`dev` פורסת רק את שירותי `dev`; דחיפה ל-`main` רק את `production`.
* Healthcheck: `/health` בשני השירותים.
* ה-Frontend פונה ל-Backend של אותה סביבה דרך הרשת הפרטית של Railway:
  `BACKEND_URL=http://backend.railway.internal:8080` (ה-Backend מאזין על `[::]:8080`, כלומר
  IPv4 ו-IPv6, כי הרשת הפרטית של Railway היא IPv6).
* אזור: ברירת המחדל של Railway (us-west2). בחירת אזור אירופי דורשת תוכנית Pro.

## Supabase — פרויקט נפרד לכל סביבה

| סביבה | פרויקט | Ref | ארגון |
|---|---|---|---|
| dev | aron-behatama-dev | `vlcdaksrnozbddwnqehk` | aron-behatama (`avomdjqmhpnfphkrolyx`) |
| production | aron-behatama-prod | `otqrdtmeusitavzpszeh` | aron-behatama |

* בסיסי נתונים, Auth, מפתחות וסודות session נפרדים לכל סביבה. אין שיתוף נתונים.
* ה-Backend מתחבר ל-Postgres דרך ה-Session pooler (`aws-0-eu-central-1.pooler.supabase.com:5432`)
  עם service role; RLS מופעל על כל הטבלאות ללא policies ציבוריות, והשרת מבצע בדיקות
  הרשאה מפורשות בכל endpoint.
* Auth: JWT חתומים ב-ES256 ומאומתים בשרת דרך JWKS (`/auth/v1/.well-known/jwks.json`).
* **הגדרה ידנית שנותרה:** ב-Supabase Dashboard → Authentication → URL Configuration, הגדירו
  Site URL וכתובת Redirect לדומיין ה-Frontend של אותה סביבה. ההתחברות בסיסמה עובדת גם בלי
  זה; ההגדרה נדרשת לזרימות דוא״ל (איפוס סיסמה) אם יופעלו.

## Migrations — Supabase CLI (מומלץ)

המאגר מקושר ל-Supabase דרך ה-CLI (`supabase/config.toml`, `supabase/migrations/`). קובץ
ה-migration זהה ל-`backend/migrations/0001_init.sql` ורשום בהיסטוריית ה-migrations של שני הפרויקטים.

```bash
supabase link --project-ref vlcdaksrnozbddwnqehk     # dev   (יבקש את סיסמת ה-DB)
supabase link --project-ref otqrdtmeusitavzpszeh     # production
supabase migration list                               # מה הוחל מקומית מול מרוחק
supabase db push --dry-run                            # מה ייושם
supabase db push                                      # יישום בפועל
```

migration חדש: `supabase migration new <name>` → כתיבת SQL אידמפוטנטי ב-`supabase/migrations/` (ולהעתיק
גם ל-`backend/migrations/` כדי שהדמו ב-SQLite יישאר תואם) → `db push` ל-dev → בדיקה → `db push` ל-production.

## Migrations — סקריפט הפרויקט (חלופה / דמו)

מריצים באופן מבוקר, לא מכל worker:

```bash
cd backend
# .env עם DEMO_MODE=false, DATABASE_URL, SUPABASE_URL של הסביבה
python scripts/run_migrations.py
```

הקובץ `migrations/0001_init.sql` הורץ בשתי הסביבות. migrations חדשים: להוסיף קובץ
`000N_*.sql`, להריץ בסביבת dev, לבדוק, ואז בייצור לפני מיזוג הקוד שתלוי בהם.

## תהליך העבודה

```
פיתוח בענף dev  →  פריסה אוטומטית ל-dev  →  בדיקה ב-frontend-dev  →
מיזוג מאושר (PR) ל-main  →  פריסה אוטומטית ל-production
```

* אין מיזוג אוטומטי מ-`dev` ל-`main`. אין force push.
* לפני מיזוג לייצור: `pytest` ירוק, בדיקה ידנית ב-dev, migrations הורצו בייצור אם נדרש.

## סודות

הסודות מוגדרים רק במשתני הסביבה של Railway (ולא ב-Git). לרשימה: `docs/env-reference.md`.
