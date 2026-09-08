"""מחירון פיתוח לדוגמה.

⚠️ המחירים כאן הם ערכי הדגמה בלבד ואינם מחירי שוק מאומתים.
שיעור המע"מ (18%) הוא ערך לדוגמה שיש לאמת מול רואה החשבון של העסק.
"""
from decimal import Decimal

from app.schemas.pricing import PriceBookItem, PriceBookSettings


def _item(code, category, name_he, unit, price, **kw) -> PriceBookItem:
    return PriceBookItem(id=code, code=code, category=category, name_he=name_he, unit=unit,
                         unit_price=Decimal(price), **kw)


DEV_SETTINGS = PriceBookSettings(
    waste_rate=Decimal("0.12"),
    vat_rate=Decimal("0.18"),
    quote_validity_days=14,
    base_labor_price=Decimal("1200"),
    labor_per_door=Decimal("150"),
    labor_per_drawer=Decimal("90"),
    labor_per_shelf=Decimal("25"),
    confirmed_by_carpenter=False,
)

DEV_ITEMS: list[PriceBookItem] = [
    # חומרי גוף (מחיר למ"ר, לפני מע"מ)
    _item("SANDWICH17", "material", "סנדוויץ׳ 17 מ״מ", "sqm", "160"),
    _item("MDF18", "material", "MDF 18 מ״מ", "sqm", "120"),
    _item("MELAMINE18", "material", "מלמין 18 מ״מ", "sqm", "110"),
    # גב
    _item("HDF3", "back_material", "גב HDF 3 מ״מ", "sqm", "35"),
    # חזיתות
    _item("MDF_COATED", "material", "חזית MDF מצופה", "sqm", "220"),
    _item("OAK_VENEER", "material", "חזית פורניר אלון", "sqm", "340"),
    _item("MELAMINE_FRONT", "material", "חזית מלמין", "sqm", "140"),
    # גימורים (למ"ר חזית)
    _item("FIN_OAK_LIGHT", "finish", "גימור אלון בהיר", "sqm", "60"),
    _item("FIN_WALNUT", "finish", "גימור אגוז", "sqm", "70"),
    _item("FIN_WHITE_MATTE", "finish", "גימור לבן מט", "sqm", "50"),
    _item("FIN_LACQUER", "finish", "לכה בגוון לבחירה", "sqm", "120"),
    # פרזול
    _item("HINGE_SET", "hardware", "חבילת פרזול לדלת (צירים, ידית)", "door", "95"),
    _item("SOFT_CLOSE", "hardware", "תוספת טריקה שקטה (לדלת/מגירה)", "unit", "40"),
    _item("DRAWER_PKG", "drawer", "חבילת מגירה פנימית (מסילות, גוף מגירה, חזית)", "drawer", "280",
          includes_soft_close=False),
    # שירותים
    _item("INSTALL", "service", "התקנה", "fixed", "650"),
    _item("DELIVERY_CENTER", "delivery", "הובלה — מרכז (גוש דן)", "trip", "350"),
    _item("DELIVERY_SHARON", "delivery", "הובלה — שרון ושפלה", "trip", "450"),
    _item("DELIVERY_NORTH", "delivery", "הובלה — צפון", "trip", "700"),
    _item("DELIVERY_SOUTH", "delivery", "הובלה — דרום", "trip", "650"),
]
