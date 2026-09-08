"""יצירת נגר מורשה: משתמש ב-Supabase Auth + שורה ב-admin_users.

אין הרשמה ציבורית. הסיסמה אינה נשמרת בקוד: היא מוזנת אינטראקטיבית או
דרך משתנה סביבה חד-פעמי ADMIN_PASSWORD (מומלץ למחוק אחרי הריצה).

שימוש:
  python scripts/create_admin_user.py --email carpenter@example.com --name "יוסי הנגר"
דורש: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL (ב-.env או בסביבה).
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.repositories.customer_repo import AdminRepository  # noqa: E402
from app.repositories.db import Database  # noqa: E402


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    settings = load_settings()
    if settings.demo_mode:
        raise SystemExit("במצב דמו אין צורך במשתמש Supabase — השתמשו בכפתור 'כניסת דמו'")
    if not settings.supabase_service_role_key:
        raise SystemExit("חסר SUPABASE_SERVICE_ROLE_KEY")

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("סיסמה לנגר (לא תוצג): ")
    if len(password) < 10:
        raise SystemExit("הסיסמה חייבת להיות לפחות 10 תווים")

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    existing = _find_user(client, args.email)
    if existing:
        user_id = existing.id
        client.auth.admin.update_user_by_id(user_id, {"password": password, "email_confirm": True})
        print(f"משתמש קיים עודכן: {args.email}")
    else:
        created = client.auth.admin.create_user(
            {"email": args.email, "password": password, "email_confirm": True,
             "user_metadata": {"display_name": args.name, "role": "carpenter"}})
        user_id = created.user.id
        print(f"נוצר משתמש Auth: {args.email}")

    db = Database.postgres(settings.database_url)
    AdminRepository(db).upsert(user_id, args.email, args.name)
    print(f"הנגר {args.name} מורשה (admin_users). auth_user_id={user_id}")


def _find_user(client, email: str):
    page = client.auth.admin.list_users(page=1, per_page=200)
    users = page if isinstance(page, list) else getattr(page, "users", [])
    return next((u for u in users if (u.email or "").lower() == email.lower()), None)


if __name__ == "__main__":
    main()
