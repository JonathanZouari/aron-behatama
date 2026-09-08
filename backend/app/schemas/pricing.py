"""מודלי תמחור: מחירון, סעיפי מחיר ותוצאת חישוב. כסף ב-Decimal בלבד."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PriceCategory = Literal[
    "material", "back_material", "finish", "hardware", "drawer", "labor", "delivery", "service"
]


class PriceBookItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    code: str = Field(min_length=1, max_length=40)
    category: PriceCategory
    name_he: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=20)  # sqm | unit | door | drawer | fixed | trip
    unit_price: Decimal = Field(ge=0)
    active: bool = True
    # למשל: חבילת מגירה שכוללת טריקה שקטה
    includes_soft_close: bool = False
    description_he: Optional[str] = Field(default=None, max_length=500)


class PriceBookSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waste_rate: Decimal = Field(default=Decimal("0.12"), ge=0, le=1)
    vat_rate: Decimal = Field(default=Decimal("0.18"), ge=0, le=1)
    quote_validity_days: int = Field(default=14, ge=1, le=365)
    base_labor_price: Decimal = Field(default=Decimal("0"), ge=0)
    labor_per_door: Decimal = Field(default=Decimal("0"), ge=0)
    labor_per_drawer: Decimal = Field(default=Decimal("0"), ge=0)
    labor_per_shelf: Decimal = Field(default=Decimal("0"), ge=0)
    back_material_code: str = "HDF3"
    door_hardware_code: str = "HINGE_SET"
    drawer_package_code: str = "DRAWER_PKG"
    soft_close_code: str = "SOFT_CLOSE"
    installation_code: str = "INSTALL"
    # הנגר אימת שהמחירון ושיעור המס נכונים (נדרש לפרסום בייצור)
    confirmed_by_carpenter: bool = False


class PriceBook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int
    is_demo: bool = False
    settings: PriceBookSettings
    items: list[PriceBookItem]

    def find(self, code: str) -> Optional[PriceBookItem]:
        for item in self.items:
            if item.code == code and item.active:
                return item
        return None


class ManualAdjustment(BaseModel):
    """סעיף ידני של הנגר. חייב הסבר."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=2, max_length=200)
    amount: Decimal
    reason: str = Field(min_length=3, max_length=500)


class PriceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal
    kind: Literal["auto", "manual"] = "auto"
    reason: Optional[str] = None


class PricingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricebook_id: str
    pricebook_version: int
    lines: list[PriceLine]
    subtotal: Optional[Decimal]  # לפני מע"מ
    vat_rate: Decimal
    vat_amount: Optional[Decimal]
    total: Optional[Decimal]
    # דרישות שלא תומחרו אוטומטית — הנגר חייב לטפל בהן לפני פרסום
    manual_required: list[str]
    is_complete: bool
    areas_sqm: dict[str, str] = Field(default_factory=dict)
