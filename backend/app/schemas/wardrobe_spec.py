"""סכמת מפרט הארון.

ערך חסר הוא None (לא אפס). אפס הוא ערך תקין למשל למגירות כאשר הלקוח ביקש
במפורש "בלי מגירות". הטווחים העסקיים ניתנים לשינוי ב-SpecLimits; חריגה
מטווח אינה שגיאה אלא סיבה לבדיקה ידנית.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class SpecLimits(BaseModel):
    """טווחים נתמכים לייצור אוטומטי. מחוצה להם → בדיקה ידנית."""

    width_cm: tuple[int, int] = (60, 400)
    height_cm: tuple[int, int] = (100, 280)
    depth_cm: tuple[int, int] = (35, 80)
    doors: tuple[int, int] = (1, 8)
    internal_drawers: tuple[int, int] = (0, 8)
    shelves: tuple[int, int] = (0, 20)
    compartments: tuple[int, int] = (1, 8)


DEFAULT_LIMITS = SpecLimits()

# שדות שחובה למלא כדי לחשב מחיר אוטומטי
REQUIRED_FOR_PRICING = (
    "width_cm",
    "height_cm",
    "depth_cm",
    "body_material_id",
    "front_material_id",
    "finish_id",
    "doors",
    "internal_drawers",
    "shelves",
    "compartments",
    "soft_close",
    "delivery",
    "installation",
)

FIELD_LABELS_HE = {
    "width_cm": "רוחב",
    "height_cm": "גובה",
    "depth_cm": "עומק",
    "body_material_id": "חומר גוף",
    "front_material_id": "חומר חזיתות",
    "finish_id": "גימור",
    "color": "צבע",
    "doors": "מספר דלתות",
    "internal_drawers": "מגירות פנימיות",
    "shelves": "מדפים",
    "compartments": "תאים אנכיים",
    "soft_close": "טריקה שקטה",
    "delivery": "הובלה",
    "installation": "התקנה",
    "city": "עיר",
    "customer_notes": "הערות",
    "special_requirements": "דרישות מיוחדות",
}


class SpecFields(BaseModel):
    """השדות המשותפים למפרט מלא ולעדכון חלקי."""

    model_config = ConfigDict(extra="forbid")

    width_cm: Optional[int] = Field(default=None, ge=1, le=2000)
    height_cm: Optional[int] = Field(default=None, ge=1, le=2000)
    depth_cm: Optional[int] = Field(default=None, ge=1, le=2000)
    body_material_id: Optional[str] = Field(default=None, max_length=40)
    front_material_id: Optional[str] = Field(default=None, max_length=40)
    finish_id: Optional[str] = Field(default=None, max_length=40)
    color: Optional[str] = Field(default=None, max_length=80)
    doors: Optional[int] = Field(default=None, ge=0, le=50)
    internal_drawers: Optional[int] = Field(default=None, ge=0, le=50)
    shelves: Optional[int] = Field(default=None, ge=0, le=100)
    compartments: Optional[int] = Field(default=None, ge=1, le=50)
    soft_close: Optional[StrictBool] = None
    delivery: Optional[StrictBool] = None
    installation: Optional[StrictBool] = None
    city: Optional[str] = Field(default=None, max_length=80)
    customer_notes: Optional[str] = Field(default=None, max_length=2000)
    special_requirements: Optional[str] = Field(default=None, max_length=2000)


class WardrobeSpec(SpecFields):
    """מפרט ארון מלבני עם דלתות ציר."""

    product_type: str = "wardrobe"

    def missing_fields(self) -> list[str]:
        """שדות הנחוצים לתמחור שעדיין לא נמסרו. עיר נדרשת רק להובלה/התקנה."""
        missing = [f for f in REQUIRED_FOR_PRICING if getattr(self, f) is None]
        if (self.delivery or self.installation) and not self.city:
            missing.append("city")
        return missing

    def out_of_range_reasons(self, limits: SpecLimits = DEFAULT_LIMITS) -> list[str]:
        """סיבות לבדיקה ידנית הנובעות מחריגה מטווח נתמך."""
        checks = {
            "width_cm": limits.width_cm,
            "height_cm": limits.height_cm,
            "depth_cm": limits.depth_cm,
            "doors": limits.doors,
            "internal_drawers": limits.internal_drawers,
            "shelves": limits.shelves,
            "compartments": limits.compartments,
        }
        reasons = []
        for field, (lo, hi) in checks.items():
            value = getattr(self, field)
            if value is not None and not lo <= value <= hi:
                label = FIELD_LABELS_HE[field]
                reasons.append(f"{label} ({value}) מחוץ לטווח הנתמך {lo}–{hi}")
        return reasons


class SpecPatch(SpecFields):
    """עדכון חלקי למפרט. רק שדות שנשלחו במפורש מוחלפים."""


def apply_patch(spec: WardrobeSpec, patch: SpecPatch) -> WardrobeSpec:
    """מחזיר מפרט חדש (ללא מוטציה) עם השדות שנשלחו ב-patch."""
    changes = patch.model_dump(exclude_unset=True)
    return spec.model_copy(update=changes)


def spec_diff(before: WardrobeSpec, after: WardrobeSpec) -> dict[str, dict]:
    """הבדלים בין שני מפרטים: {field: {"before": x, "after": y}}."""
    b, a = before.model_dump(), after.model_dump()
    return {k: {"before": b[k], "after": a[k]} for k in a if a[k] != b[k]}
