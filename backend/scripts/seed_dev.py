"""טעינת קטלוג, מחירון לדוגמה ופניות הדגמה לסביבת פיתוח. חסום בייצור.

שימוש:
  python scripts/seed_dev.py                    # קטלוג + מחירון דוגמה (בטוח להרצה חוזרת)
  python scripts/seed_dev.py --with-inquiries   # גם פניות לדוגמה (פעם אחת)
  python scripts/seed_dev.py --catalog-only     # קטלוג בלבד — האפשרות היחידה המותרת בייצור
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
    catalog_only = "--catalog-only" in sys.argv
    if settings.is_production and not catalog_only:
        raise SystemExit("אין לטעון נתוני הדגמה בייצור (APP_ENV=production). מותר רק --catalog-only")
    container = build_container(settings)
    if catalog_only:
        seed_reference_data(container, include_pricebook=False)
        print("נטען קטלוג בלבד")
        return
    container.db.run_migrations()
    if "--with-inquiries" in sys.argv:
        seed_demo(container)
        print("נטענו קטלוג, מחירון ופניות לדוגמה")
    else:
        seed_reference_data(container)
        print("נטענו קטלוג ומחירון לדוגמה")


if __name__ == "__main__":
    main()
