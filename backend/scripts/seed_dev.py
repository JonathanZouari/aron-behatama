"""טעינת קטלוג, מחירון לדוגמה ופניות הדגמה לסביבת פיתוח. חסום בייצור.

שימוש:
  python scripts/seed_dev.py                 # קטלוג + מחירון (בטוח להרצה חוזרת)
  python scripts/seed_dev.py --with-inquiries  # גם פניות לדוגמה (פעם אחת)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.container import build_container  # noqa: E402
from app.seed.demo_data import seed_demo, seed_reference_data  # noqa: E402


def main() -> None:
    load_dotenv()
    settings = load_settings()
    if settings.is_production:
        raise SystemExit("אין לטעון נתוני הדגמה בייצור (APP_ENV=production)")
    container = build_container(settings)
    container.db.run_migrations()
    if "--with-inquiries" in sys.argv:
        seed_demo(container)
        print("נטענו קטלוג, מחירון ופניות לדוגמה")
    else:
        seed_reference_data(container)
        print("נטענו קטלוג ומחירון לדוגמה")


if __name__ == "__main__":
    main()
