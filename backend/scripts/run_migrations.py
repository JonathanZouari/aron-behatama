"""הרצת migrations מבוקרת (לא אוטומטית מכל worker).

שימוש:  python scripts/run_migrations.py
קורא את משתני הסביבה (או .env). בדמו — SQLite; אחרת DATABASE_URL של Supabase.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.repositories.db import Database  # noqa: E402


def main() -> None:
    load_dotenv()
    settings = load_settings()
    db = Database.sqlite(settings.sqlite_path) if settings.demo_mode else Database.postgres(settings.database_url)
    applied = db.run_migrations()
    print(f"[{settings.app_env}] {db.kind}: הורצו {len(applied)} migrations: {applied or 'אין חדשים'}")


if __name__ == "__main__":
    main()
