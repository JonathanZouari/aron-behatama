"""בדיקות מנוע התמחור: נוסחאות, פחת, התאמות, מע"מ, עיגול, חוסר מידע."""
from decimal import Decimal

import pytest

from app.schemas.pricing import ManualAdjustment, PriceBook, PriceBookItem, PriceBookSettings
from app.schemas.wardrobe_spec import WardrobeSpec
from app.services.pricing_engine import PricingError, compute_areas, price_spec


def _item(code, category, unit, price, **kw):
    return PriceBookItem(id=code, code=code, category=category, name_he=code, unit=unit, unit_price=Decimal(price), **kw)


@pytest.fixture
def pricebook():
    return PriceBook(
        id="pb1",
        version=1,
        is_demo=True,
        settings=PriceBookSettings(
            waste_rate=Decimal("0.10"),
            vat_rate=Decimal("0.18"),
            base_labor_price=Decimal("1000"),
            labor_per_door=Decimal("100"),
            labor_per_drawer=Decimal("50"),
            labor_per_shelf=Decimal("20"),
        ),
        items=[
            _item("SANDWICH17", "material", "sqm", "150"),
            _item("MDF18", "material", "sqm", "120"),
            _item("HDF3", "back_material", "sqm", "40"),
            _item("OAK_LIGHT", "finish", "sqm", "80"),
            _item("HINGE_SET", "hardware", "door", "90"),
            _item("DRAWER_PKG", "drawer", "drawer", "250", includes_soft_close=False),
            _item("SOFT_CLOSE", "hardware", "door", "35"),
            _item("INSTALL", "service", "fixed", "600"),
            _item("DELIVERY_CENTER", "delivery", "trip", "350"),
        ],
    )


@pytest.fixture
def full_spec():
    return WardrobeSpec(
        width_cm=200, height_cm=250, depth_cm=60,
        body_material_id="SANDWICH17", front_material_id="MDF18", finish_id="OAK_LIGHT",
        doors=4, internal_drawers=2, shelves=6, compartments=2,
        soft_close=True, delivery=True, installation=True, city="תל אביב",
    )


def test_area_formulas(full_spec):
    areas = compute_areas(full_spec)
    # W=2, H=2.5, D=0.6
    assert areas["body"] == Decimal("2") * Decimal("2.5") * Decimal("0.6") + Decimal("2") * Decimal("2") * Decimal("0.6")
    assert areas["back"] == Decimal("5.0")
    assert areas["fronts"] == Decimal("5.0")
    assert areas["partitions"] == Decimal("1") * Decimal("2.5") * Decimal("0.6")  # (2-1)*H*D
    assert areas["shelves"] == Decimal("6") * (Decimal("2") / Decimal("2")) * Decimal("0.6")


def test_full_price_is_deterministic_and_rounded(full_spec, pricebook):
    result = price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER")
    assert result.is_complete
    assert result.manual_required == []
    codes = [line.code for line in result.lines]
    # כל שלב מופיע פעם אחת בלבד — אין חיוב כפול
    assert len(codes) == len(set(codes))
    for line in result.lines:
        assert line.total == line.total.quantize(Decimal("0.01"))
    assert result.subtotal == sum(line.total for line in result.lines)
    assert result.vat_amount == (result.subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    assert result.total == result.subtotal + result.vat_amount
    # קריאה חוזרת נותנת תוצאה זהה
    assert price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER") == result


def test_waste_applies_only_to_panels(full_spec, pricebook):
    result = price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER")
    by_code = {line.code: line for line in result.lines}
    areas = compute_areas(full_spec)
    body_area = areas["body"] + areas["partitions"] + areas["shelves"]
    expected_body = (body_area * Decimal("150") * Decimal("1.10")).quantize(Decimal("0.01"))
    assert by_code["SANDWICH17"].total == expected_body
    # גימור ללא פחת
    assert by_code["OAK_LIGHT"].total == (areas["fronts"] * Decimal("80")).quantize(Decimal("0.01"))
    # פרזול לפי דלת ללא פחת
    assert by_code["HINGE_SET"].total == Decimal("360.00")


def test_soft_close_not_double_charged_when_included_in_drawer_package(full_spec, pricebook):
    result = price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER")
    assert any(l.code == "SOFT_CLOSE" for l in result.lines)
    included = pricebook.model_copy(update={
        "items": [i.model_copy(update={"includes_soft_close": True}) if i.code == "DRAWER_PKG" else i for i in pricebook.items]
    })
    result2 = price_spec(full_spec, included, delivery_zone_code="DELIVERY_CENTER")
    # טריקה שקטה עדיין נדרשת לדלתות, אך כמות המגירות אינה נספרת
    soft = next(l for l in result2.lines if l.code == "SOFT_CLOSE")
    assert soft.quantity == Decimal("4")
    soft1 = next(l for l in result.lines if l.code == "SOFT_CLOSE")
    assert soft1.quantity == Decimal("6")


def test_missing_fields_block_full_quote(pricebook):
    spec = WardrobeSpec(width_cm=200, height_cm=250)  # חסר עומק ועוד
    result = price_spec(spec, pricebook)
    assert not result.is_complete
    assert result.total is None
    assert any("חסר" in r for r in result.manual_required)


def test_missing_delivery_zone_price_requires_manual(full_spec, pricebook):
    result = price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_MOON")
    assert not result.is_complete
    assert any("הובלה" in r for r in result.manual_required)
    # שאר הסעיפים עדיין מחושבים כדי לעזור לנגר
    assert any(l.code == "SANDWICH17" for l in result.lines)


def test_special_requirements_are_not_silently_dropped(full_spec, pricebook):
    spec = full_spec.model_copy(update={"special_requirements": "דלתות הזזה בבקשה"})
    result = price_spec(spec, pricebook, delivery_zone_code="DELIVERY_CENTER")
    assert not result.is_complete
    assert any("דרישה מיוחדת" in r for r in result.manual_required)


def test_manual_adjustment_requires_reason_and_total_not_negative(full_spec, pricebook):
    with pytest.raises(Exception):
        ManualAdjustment(description="הנחה", amount=Decimal("-100"), reason="")
    adj = ManualAdjustment(description="הנחה", amount=Decimal("-100"), reason="לקוח חוזר")
    result = price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER", adjustments=[adj])
    assert any(l.kind == "manual" and l.total == Decimal("-100.00") for l in result.lines)
    huge = ManualAdjustment(description="הנחה", amount=Decimal("-999999"), reason="בדיקה")
    with pytest.raises(PricingError):
        price_spec(full_spec, pricebook, delivery_zone_code="DELIVERY_CENTER", adjustments=[huge])


def test_rounding_half_up():
    from app.services.pricing_engine import money
    assert money(Decimal("1.005")) == Decimal("1.01")
    assert money(Decimal("1.004")) == Decimal("1.00")


def test_zero_drawers_is_valid_not_missing(full_spec, pricebook):
    spec = full_spec.model_copy(update={"internal_drawers": 0})
    result = price_spec(spec, pricebook, delivery_zone_code="DELIVERY_CENTER")
    assert result.is_complete
    assert not any(l.code == "DRAWER_PKG" for l in result.lines)


def test_inactive_item_triggers_manual(full_spec, pricebook):
    pb = pricebook.model_copy(update={
        "items": [i.model_copy(update={"active": False}) if i.code == "MDF18" else i for i in pricebook.items]
    })
    result = price_spec(full_spec, pb, delivery_zone_code="DELIVERY_CENTER")
    assert not result.is_complete
    assert any("חזיתות" in r for r in result.manual_required)
