"""מטריצת תמחור דרך ה-API: וריאציות מפרט, השוואה עצמאית לנוסחאות, אינווריאנטים."""
from decimal import Decimal, ROUND_HALF_UP

import pytest

from .conftest import FULL, data

CENT = Decimal("0.01")


def _q(v):
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


def expected_lines(spec, book, zone):
    """חישוב עצמאי לפי docs/pricing-model.md כדי לאמת את השרת."""
    s = book["settings"]; items = {i["code"]: i for i in book["items"] if i["active"]}
    w, h, d = Decimal(spec["width_cm"]) / 100, Decimal(spec["height_cm"]) / 100, Decimal(spec["depth_cm"]) / 100
    comp, shelves = Decimal(spec["compartments"]), Decimal(spec["shelves"])
    body = 2 * h * d + 2 * w * d + max(comp - 1, 0) * h * d + shelves * (w / comp) * d
    waste = 1 + Decimal(s["waste_rate"])
    P = lambda c: Decimal(items[c]["unit_price"])
    out = {
        spec["body_material_id"]: _q(body * P(spec["body_material_id"]) * waste),
        s["back_material_code"]: _q(w * h * P(s["back_material_code"]) * waste),
        spec["front_material_id"]: _q(w * h * P(spec["front_material_id"]) * waste),
        spec["finish_id"]: _q(w * h * P(spec["finish_id"])),
        "LABOR": _q(Decimal(s["base_labor_price"]) + spec["doors"] * Decimal(s["labor_per_door"])
                    + spec["internal_drawers"] * Decimal(s["labor_per_drawer"]) + shelves * Decimal(s["labor_per_shelf"])),
    }
    if spec["doors"]:
        out["HINGE_SET"] = _q(spec["doors"] * P("HINGE_SET"))
    if spec["internal_drawers"]:
        out["DRAWER_PKG"] = _q(spec["internal_drawers"] * P("DRAWER_PKG"))
    if spec["soft_close"]:
        qty = spec["doors"] + (spec["internal_drawers"] if not items["DRAWER_PKG"]["includes_soft_close"] else 0)
        out["SOFT_CLOSE"] = _q(qty * P("SOFT_CLOSE"))
    if spec["delivery"]:
        out[zone] = _q(P(zone))
    if spec["installation"]:
        out["INSTALL"] = _q(P("INSTALL"))
    return out


VARIANTS = [
    {}, {"width_cm": 60, "height_cm": 100, "depth_cm": 35, "doors": 1, "compartments": 1, "shelves": 0, "internal_drawers": 0},
    {"width_cm": 400, "height_cm": 280, "depth_cm": 80, "doors": 8, "compartments": 8, "shelves": 20, "internal_drawers": 8},
    {"soft_close": False}, {"internal_drawers": 0}, {"shelves": 0}, {"compartments": 1},
    {"delivery": False, "installation": False}, {"delivery": True, "installation": False},
    {"delivery": False, "installation": True}, {"body_material_id": "MDF18"}, {"body_material_id": "MELAMINE18"},
    {"front_material_id": "OAK_VENEER"}, {"front_material_id": "MELAMINE_FRONT"}, {"finish_id": "FIN_WALNUT"},
    {"finish_id": "FIN_WHITE_MATTE"}, {"finish_id": "FIN_LACQUER", "color": "כחול"},
    {"city": "חיפה"}, {"city": "רעננה"}, {"city": "באר שבע"}, {"width_cm": 123, "height_cm": 217, "depth_cm": 47, "doors": 3, "compartments": 3, "shelves": 7},
    {"doors": 2, "internal_drawers": 1, "shelves": 1, "compartments": 2},
]
ZONES = {"תל אביב": "DELIVERY_CENTER", "חיפה": "DELIVERY_NORTH", "רעננה": "DELIVERY_SHARON", "באר שבע": "DELIVERY_SOUTH"}


@pytest.mark.parametrize("variant", VARIANTS, ids=[str(i) for i in range(len(VARIANTS))])
def test_server_pricing_matches_independent_formula(customer, admin, variant):
    spec = {**FULL, **variant}
    inq = customer.submitted_inquiry(patch=spec, city=spec["city"])
    q = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []}))
    book = data(admin.get("/api/admin/pricebook"))["active"]
    exp = expected_lines(spec, book, ZONES[spec["city"]])
    got = {i["code"]: Decimal(i["total"]) for i in q["items"]}
    assert got == exp, {k: (got.get(k), exp.get(k)) for k in set(got) | set(exp) if got.get(k) != exp.get(k)}
    subtotal = sum(exp.values())
    assert Decimal(q["subtotal"]) == subtotal
    assert Decimal(q["vat_amount"]) == _q(subtotal * Decimal(book["settings"]["vat_rate"]))
    assert Decimal(q["total"]) == subtotal + Decimal(q["vat_amount"])
    assert q["pricing"]["is_complete"] and q["pricing"]["manual_required"] == []


def test_all_line_totals_have_two_decimals(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "width_cm": 137, "height_cm": 213, "depth_cm": 59})
    q = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []}))
    for i in q["items"]:
        assert Decimal(i["total"]) == Decimal(i["total"]).quantize(CENT)


def test_no_duplicate_line_codes(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []}))
    codes = [i["code"] for i in q["items"] if i["kind"] == "auto"]
    assert len(codes) == len(set(codes))


def test_bigger_wardrobe_costs_more(customer, admin):
    small = customer.submitted_inquiry(patch={**FULL, "width_cm": 120})
    big = customer.submitted_inquiry(patch={**FULL, "width_cm": 360})
    a = data(admin.post(f"/api/admin/inquiries/{small['id']}/quotes/recalculate", {"adjustments": []}))["total"]
    b = data(admin.post(f"/api/admin/inquiries/{big['id']}/quotes/recalculate", {"adjustments": []}))["total"]
    assert Decimal(b) > Decimal(a)


def test_soft_close_included_in_drawer_package_not_double_charged(customer, admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    items = [{**i, "includes_soft_close": True} if i["code"] == "DRAWER_PKG" else i for i in book["items"]]
    admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": items, "is_demo": True})
    try:
        inq = customer.submitted_inquiry()
        q = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []}))
        soft = next(i for i in q["items"] if i["code"] == "SOFT_CLOSE")
        assert Decimal(soft["quantity"]) == Decimal(FULL["doors"])
    finally:
        admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": book["items"], "is_demo": True})
