"""מנוע תמחור דטרמיניסטי.

מודל הערכה מסחרי לדוגמה (לא רשימת חיתוך ולא חישוב הנדסי). W, H, D במטרים:
    שטח גוף      = 2·H·D + 2·W·D
    שטח גב       = W·H
    שטח חזיתות   = W·H
    שטח מחיצות   = max(תאים−1, 0)·H·D
    שטח מדפים    = מדפים·(W/תאים)·D

סדר החישוב (ראו docs/pricing-model.md):
 1. לוחות גוף+מחיצות+מדפים לפי חומר הגוף      6. פרזול לכל דלת
 2. גב לפי חומר גב                              7. חבילת מגירה
 3. חזיתות לפי חומר החזיתות                     8. טריקה שקטה (אם לא כלולה)
 4. פחת על לוחות (1–3) בלבד                     9. עבודה בסיסית + תוספות
 5. גימור חזיתות לפי שטח                       10. הובלה  11. התקנה
12. התאמות ידניות של הנגר   13. מע"מ

כלל עיגול: כל סעיף מעוגל לאגורה (ROUND_HALF_UP) בנפרד; הסכומים הם סכום
הסעיפים המעוגלים. מע"מ מעוגל פעם אחת על הסכום לפני מע"מ.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.schemas.pricing import ManualAdjustment, PriceBook, PriceBookItem, PriceLine, PricingResult
from app.schemas.wardrobe_spec import FIELD_LABELS_HE, WardrobeSpec

CENT = Decimal("0.01")
CM_PER_M = Decimal("100")


class PricingError(Exception):
    """שגיאה עסקית בתמחור (למשל מחיר סופי שלילי)."""


def money(value: Decimal) -> Decimal:
    """עיגול לאגורה, חצי כלפי מעלה. כלל העיגול היחיד במערכת."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_areas(spec: WardrobeSpec) -> dict[str, Decimal]:
    """שטחים במ"ר לפי מודל ההערכה. מניח שכל שדות המידות והחלוקה מלאים."""
    if spec.width_cm is None or spec.height_cm is None or spec.depth_cm is None:
        raise PricingError("לא ניתן לחשב שטחים ללא רוחב, גובה ועומק")
    w = Decimal(spec.width_cm) / CM_PER_M
    h = Decimal(spec.height_cm) / CM_PER_M
    d = Decimal(spec.depth_cm) / CM_PER_M
    compartments = Decimal(spec.compartments or 1)
    shelves = Decimal(spec.shelves or 0)
    return {
        "body": 2 * h * d + 2 * w * d,
        "back": w * h,
        "fronts": w * h,
        "partitions": max(compartments - 1, Decimal(0)) * h * d,
        "shelves": shelves * (w / compartments) * d,
    }


def _line(item: PriceBookItem, qty: Decimal, description: Optional[str] = None,
          multiplier: Decimal = Decimal(1)) -> PriceLine:
    return PriceLine(
        code=item.code,
        description=description or item.name_he,
        quantity=qty.quantize(Decimal("0.001")),
        unit=item.unit,
        unit_price=item.unit_price,
        total=money(qty * item.unit_price * multiplier),
    )


def _manual_line(adj: ManualAdjustment) -> PriceLine:
    return PriceLine(
        code="MANUAL",
        description=adj.description,
        quantity=Decimal(1),
        unit="fixed",
        unit_price=money(adj.amount),
        total=money(adj.amount),
        kind="manual",
        reason=adj.reason,
    )


def price_spec(
    spec: WardrobeSpec,
    pricebook: PriceBook,
    delivery_zone_code: Optional[str] = None,
    adjustments: Optional[list[ManualAdjustment]] = None,
) -> PricingResult:
    """מחשב טיוטת מחיר. אם חסר מידע — מחזיר תוצאה חלקית ללא סכום סופי."""
    settings = pricebook.settings
    lines: list[PriceLine] = []
    manual: list[str] = []

    missing = spec.missing_fields()
    if missing:
        labels = ", ".join(FIELD_LABELS_HE.get(f, f) for f in missing)
        manual.append(f"חסר מידע לתמחור: {labels}")
    manual.extend(spec.out_of_range_reasons())
    if spec.special_requirements and spec.special_requirements.strip():
        manual.append(f"דרישה מיוחדת לבדיקה ידנית: {spec.special_requirements.strip()}")

    dims_ready = None not in (spec.width_cm, spec.height_cm, spec.depth_cm, spec.compartments)
    areas = compute_areas(spec) if dims_ready else {}
    waste = Decimal(1) + settings.waste_rate

    # 1–4: לוחות (עם פחת)
    if dims_ready:
        body_item = pricebook.find(spec.body_material_id) if spec.body_material_id else None
        if body_item:
            body_area = areas["body"] + areas["partitions"] + areas["shelves"]
            lines.append(_line(body_item, body_area, f"לוחות גוף, מחיצות ומדפים — {body_item.name_he} (כולל פחת)", waste))
        elif spec.body_material_id:
            manual.append("אין מחיר פעיל לחומר הגוף שנבחר")

        back_item = pricebook.find(settings.back_material_code)
        if back_item:
            lines.append(_line(back_item, areas["back"], f"גב — {back_item.name_he} (כולל פחת)", waste))
        else:
            manual.append("אין מחיר פעיל לחומר הגב")

        front_item = pricebook.find(spec.front_material_id) if spec.front_material_id else None
        if front_item:
            lines.append(_line(front_item, areas["fronts"], f"חזיתות — {front_item.name_he} (כולל פחת)", waste))
        elif spec.front_material_id:
            manual.append("אין מחיר פעיל לחומר החזיתות שנבחר")

        # 5: גימור (ללא פחת)
        finish_item = pricebook.find(spec.finish_id) if spec.finish_id else None
        if finish_item:
            lines.append(_line(finish_item, areas["fronts"], f"גימור חזיתות — {finish_item.name_he}"))
        elif spec.finish_id:
            manual.append("אין מחיר פעיל לגימור שנבחר")

    # 6: פרזול לדלת
    doors = Decimal(spec.doors or 0)
    if doors > 0:
        hinge = pricebook.find(settings.door_hardware_code)
        if hinge:
            lines.append(_line(hinge, doors, "חבילת פרזול לדלת"))
        else:
            manual.append("אין מחיר פעיל לפרזול דלתות")

    # 7: מגירות
    drawers = Decimal(spec.internal_drawers or 0)
    drawer_pkg = pricebook.find(settings.drawer_package_code) if drawers > 0 else None
    if drawers > 0:
        if drawer_pkg:
            lines.append(_line(drawer_pkg, drawers, "חבילת מגירה פנימית"))
        else:
            manual.append("אין מחיר פעיל לחבילת מגירה")

    # 8: טריקה שקטה — רק לרכיבים שאינם כוללים אותה
    if spec.soft_close:
        soft_qty = doors
        if drawers > 0 and not (drawer_pkg and drawer_pkg.includes_soft_close):
            soft_qty += drawers
        soft_item = pricebook.find(settings.soft_close_code)
        if soft_item and soft_qty > 0:
            lines.append(_line(soft_item, soft_qty, "תוספת טריקה שקטה"))
        elif not soft_item:
            manual.append("אין מחיר פעיל לטריקה שקטה")

    # 9: עבודה
    shelves = Decimal(spec.shelves or 0)
    labor_total = (
        settings.base_labor_price
        + doors * settings.labor_per_door
        + drawers * settings.labor_per_drawer
        + shelves * settings.labor_per_shelf
    )
    lines.append(PriceLine(
        code="LABOR", description="עבודה בסיסית ותוספות לפי רכיבים", quantity=Decimal(1),
        unit="fixed", unit_price=money(labor_total), total=money(labor_total),
    ))

    # 10: הובלה
    if spec.delivery:
        zone_item = pricebook.find(delivery_zone_code) if delivery_zone_code else None
        if zone_item and zone_item.category == "delivery":
            lines.append(_line(zone_item, Decimal(1), zone_item.name_he))
        else:
            manual.append("הובלה: לא נמצא מחיר לאזור — נדרש תמחור ידני")

    # 11: התקנה
    if spec.installation:
        install_item = pricebook.find(settings.installation_code)
        if install_item:
            lines.append(_line(install_item, Decimal(1), "התקנה"))
        else:
            manual.append("אין מחיר פעיל להתקנה")

    # 12: התאמות ידניות
    for adj in adjustments or []:
        lines.append(_manual_line(adj))

    is_complete = not manual
    subtotal = sum((l.total for l in lines), Decimal(0)) if lines else Decimal(0)
    if subtotal < 0:
        raise PricingError("המחיר הסופי אינו יכול להיות שלילי")

    vat_amount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    if is_complete:
        vat_amount = money(subtotal * settings.vat_rate)
        total = subtotal + vat_amount

    return PricingResult(
        pricebook_id=pricebook.id,
        pricebook_version=pricebook.version,
        lines=lines,
        subtotal=subtotal if is_complete else None,
        vat_rate=settings.vat_rate,
        vat_amount=vat_amount,
        total=total,
        manual_required=manual,
        is_complete=is_complete,
        areas_sqm={k: str(v.quantize(Decimal("0.0001"))) for k, v in areas.items()},
    )
