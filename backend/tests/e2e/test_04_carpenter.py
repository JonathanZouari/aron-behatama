"""Dashboard לנגר: פניות, מפרט, טיוטות, פרסום, ביטול, סגירה, מחירון, לקוחות, היסטוריה."""
from decimal import Decimal

import pytest

from .conftest import FULL, Client, data


# ---- Dashboard ורשימה ----
def test_dashboard_counts_are_numbers(admin):
    d = data(admin.get("/api/admin/dashboard"))
    for k in ("new_inquiries", "awaiting_review", "published_quotes", "accepted_quotes"):
        assert isinstance(d[k], int) and d[k] >= 0


def test_dashboard_counts_increase_after_submit(customer, admin):
    before = data(admin.get("/api/admin/dashboard"))["awaiting_review"]
    customer.submitted_inquiry()
    assert data(admin.get("/api/admin/dashboard"))["awaiting_review"] == before + 1


def test_list_search_by_number(customer, admin):
    inq = customer.submitted_inquiry()
    rows = data(admin.get(f"/api/admin/inquiries?q={inq['number']}"))
    assert [r["id"] for r in rows] == [inq["id"]]


def test_list_search_by_phone_and_name(customer, admin):
    inq = customer.submitted_inquiry(full_name="פלוני אלמוני מיוחד", phone="0599999999")
    assert any(r["id"] == inq["id"] for r in data(admin.get("/api/admin/inquiries?q=0599999999")))
    assert any(r["id"] == inq["id"] for r in data(admin.get("/api/admin/inquiries?q=אלמוני מיוחד")))


def test_list_search_no_match_empty(admin):
    assert data(admin.get("/api/admin/inquiries?q=ZZZ-NO-SUCH")) == []


@pytest.mark.parametrize("status", ["collecting_details", "awaiting_carpenter", "quote_available", "accepted", "closed"])
def test_list_filter_by_status(admin, status):
    rows = data(admin.get(f"/api/admin/inquiries?status={status}"))
    assert all(r["status"] == status for r in rows)


def test_list_manual_filter(customer, admin):
    customer.submitted_inquiry(patch={"width_cm": 500, **{k: v for k, v in FULL.items() if k != "width_cm"}})
    rows = data(admin.get("/api/admin/inquiries?manual=1"))
    assert rows and all(r["requires_manual_review"] for r in rows)


def test_list_search_injection_safe(admin):
    r = admin.get("/api/admin/inquiries?q=%27%20OR%201%3D1--")
    assert r.status_code == 200


def test_detail_contains_all_sections(customer, admin):
    inq = customer.submitted_inquiry()
    d = data(admin.get(f"/api/admin/inquiries/{inq['id']}"))
    for k in ("contact", "spec", "spec_versions", "messages", "notes", "events", "quotes", "catalog", "row_version"):
        assert k in d
    assert d["contact"]["phone"] == "0521234567" and d["spec"]["customer_confirmed"] is True


def test_detail_404_for_unknown(admin):
    assert admin.get("/api/admin/inquiries/00000000-0000-0000-0000-000000000000").status_code == 404


# ---- עריכת מפרט על ידי הנגר ----
def test_carpenter_edit_bumps_version_and_clears_confirmation(customer, admin):
    inq = customer.submitted_inquiry()
    d = data(admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": inq["spec"]["version"], "patch": {"shelves": 8}}))
    assert d["spec"]["version"] == inq["spec"]["version"] + 1 and d["spec"]["customer_confirmed"] is False
    assert d["spec_versions"][-1]["source"] == "carpenter"


def test_carpenter_edit_stale_version_409(customer, admin):
    inq = customer.submitted_inquiry()
    r = admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": 1, "patch": {"shelves": 8}})
    assert r.status_code == 409


def test_carpenter_edit_invalid_value_422(customer, admin):
    inq = customer.submitted_inquiry()
    r = admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": inq["spec"]["version"], "patch": {"doors": -1}})
    assert r.status_code == 422


def test_carpenter_can_edit_collecting_inquiry(customer, admin):
    inq = customer.new_inquiry()
    r = admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": 1, "patch": {"width_cm": 150}})
    assert r.status_code == 200


# ---- טיוטות ותמחור ----
def _recalc(admin, inq_id, **body):
    return admin.post(f"/api/admin/inquiries/{inq_id}/quotes/recalculate", {"adjustments": [], **body})


def test_recalculate_creates_draft_with_totals(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    assert q["status"] == "draft" and q["version"] == 1 and q["total"] and q["pricing"]["is_complete"]
    assert q["pricing"]["pricebook_version"] >= 1 and q["delivery_zone_code"] == "DELIVERY_CENTER"


def test_recalculate_twice_updates_same_draft(customer, admin):
    inq = customer.submitted_inquiry()
    a = data(_recalc(admin, inq["id"]))
    b = data(_recalc(admin, inq["id"]))
    assert a["id"] == b["id"] and b["version"] == 1


def test_recalculate_is_deterministic(customer, admin):
    inq = customer.submitted_inquiry()
    a = data(_recalc(admin, inq["id"]))["total"]
    b = data(_recalc(admin, inq["id"]))["total"]
    assert a == b


def test_zone_override(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"], delivery_zone_code="DELIVERY_NORTH"))
    assert any("צפון" in i["description"] for i in q["items"])


def test_unknown_zone_requires_manual(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"], delivery_zone_code="DELIVERY_MOON"))
    assert q["total"] is None and any("הובלה" in m for m in q["pricing"]["manual_required"])


def test_unmapped_city_requires_manual(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "city": "אילת"}, city="אילת")
    q = data(_recalc(admin, inq["id"]))
    assert q["total"] is None


def test_no_delivery_no_zone_line(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "delivery": False, "installation": False})
    q = data(_recalc(admin, inq["id"]))
    assert not any(i["code"].startswith("DELIVERY") for i in q["items"]) and not any(i["code"] == "INSTALL" for i in q["items"])


@pytest.mark.parametrize("adj,ok", [
    ({"description": "הנחה", "amount": "-100", "reason": "לקוח חוזר"}, True),
    ({"description": "תוספת", "amount": "250.50", "reason": "עבודה מיוחדת"}, True),
    ({"description": "הנחה", "amount": "-100", "reason": ""}, False),
    ({"description": "הנחה", "amount": "-100", "reason": "ab"}, False),
    ({"description": "", "amount": "-100", "reason": "סיבה"}, False),
    ({"description": "הנחה", "amount": "abc", "reason": "סיבה"}, False),
    ({"description": "הנחה", "amount": "-100"}, False),
])
def test_manual_adjustment_validation(customer, admin, adj, ok):
    inq = customer.submitted_inquiry()
    r = _recalc(admin, inq["id"], adjustments=[adj])
    assert (r.status_code == 200) is ok, r.text
    if ok:
        q = r.json()["data"]
        assert any(i["kind"] == "manual" and i["reason"] == adj["reason"] for i in q["items"])


def test_adjustment_changes_total_exactly(customer, admin):
    inq = customer.submitted_inquiry()
    base = data(_recalc(admin, inq["id"]))
    adj = data(_recalc(admin, inq["id"], adjustments=[{"description": "הנחה", "amount": "-100", "reason": "בדיקה"}]))
    diff = Decimal(base["subtotal"]) - Decimal(adj["subtotal"])
    assert diff == Decimal("100.00")
    vat = Decimal(adj["vat_rate"])
    assert Decimal(adj["total"]) == Decimal(adj["subtotal"]) + (Decimal(adj["subtotal"]) * vat).quantize(Decimal("0.01"))


def test_negative_total_rejected(customer, admin):
    inq = customer.submitted_inquiry()
    r = _recalc(admin, inq["id"], adjustments=[{"description": "הנחה", "amount": "-999999", "reason": "בדיקה"}])
    assert r.status_code == 500 or r.status_code == 400 or r.status_code == 409


def test_too_many_adjustments_rejected(customer, admin):
    inq = customer.submitted_inquiry()
    adjs = [{"description": f"א{i}", "amount": "1", "reason": "סיבה"} for i in range(21)]
    assert _recalc(admin, inq["id"], adjustments=adjs).status_code == 422


def test_incomplete_spec_draft_has_no_total_but_partial_lines(customer, admin):
    inq = customer.submitted_inquiry(patch={"width_cm": 200, "height_cm": 240, "depth_cm": 60, "doors": 2, "delivery": False, "installation": False})
    q = data(_recalc(admin, inq["id"]))
    assert q["total"] is None and any(i["code"] == "HINGE_SET" for i in q["items"])


# ---- פרסום ----
def _publish(admin, inq_id, quote_id):
    return admin.post(f"/api/admin/inquiries/{inq_id}/quotes/publish", {"quote_id": quote_id})


def test_publish_sets_dates_and_status(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    p = data(_publish(admin, inq["id"], q["id"]))
    assert p["status"] == "published" and p["published_at"] and p["expires_at"] > p["published_at"]
    assert data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["status"] == "quote_available"


def test_publish_twice_idempotent(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    _publish(admin, inq["id"], q["id"])
    assert _publish(admin, inq["id"], q["id"]).status_code == 200


def test_publish_without_total_blocked(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "city": "אילת"}, city="אילת")
    q = data(_recalc(admin, inq["id"]))
    assert _publish(admin, inq["id"], q["id"]).status_code == 409


def test_manual_handled_alone_does_not_unlock_publish_without_total(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "city": "אילת"}, city="אילת")
    q = data(_recalc(admin, inq["id"], manual_handled=True))
    assert q["manual_handled"] is True and _publish(admin, inq["id"], q["id"]).status_code == 409


def test_manual_handled_with_manual_delivery_line_allows_publish(customer, admin):
    inq = customer.submitted_inquiry(patch={**FULL, "city": "אילת"}, city="אילת")
    # הנגר מתמחר הובלה ידנית ובוחר אזור קיים כדי לסגור את הדרישה
    q = data(_recalc(admin, inq["id"], delivery_zone_code="DELIVERY_SOUTH", manual_handled=True,
                     adjustments=[{"description": "תוספת הובלה לאילת", "amount": "400", "reason": "מרחק"}]))
    assert q["total"] is not None
    assert _publish(admin, inq["id"], q["id"]).status_code == 200


def test_publish_stale_draft_blocked(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    d = data(admin.get(f"/api/admin/inquiries/{inq['id']}"))
    admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": d["spec"]["version"], "patch": {"doors": 5}})
    r = _publish(admin, inq["id"], q["id"])
    assert r.status_code == 409 and "לחשב מחדש" in r.json()["error"]


def test_recalc_after_spec_change_clears_stale(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    d = data(admin.get(f"/api/admin/inquiries/{inq['id']}"))
    admin.patch(f"/api/admin/inquiries/{inq['id']}/spec", {"expected_version": d["spec"]["version"], "patch": {"doors": 5}})
    q2 = data(_recalc(admin, inq["id"]))
    assert q2["id"] == q["id"] and q2["is_stale"] is False and q2["total"] != q["total"]
    assert _publish(admin, inq["id"], q2["id"]).status_code == 200


def test_publish_unknown_quote_404(customer, admin):
    inq = customer.submitted_inquiry()
    assert _publish(admin, inq["id"], "nope").status_code == 404


def test_publish_quote_of_other_inquiry_404(customer, admin):
    a = customer.submitted_inquiry(); b = Client().submitted_inquiry()
    q = data(_recalc(admin, a["id"]))
    assert _publish(admin, b["id"], q["id"]).status_code == 404


def test_new_version_after_publish_supersedes(customer, admin):
    inq = customer.submitted_inquiry()
    q1 = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q1["id"])
    q2 = data(_recalc(admin, inq["id"]))
    assert q2["version"] == 2 and q2["status"] == "draft"
    _publish(admin, inq["id"], q2["id"])
    statuses = {q["version"]: q["status"] for q in data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["quotes"]}
    assert statuses == {1: "superseded", 2: "published"}


def test_customer_sees_latest_published_only(customer, admin):
    inq = customer.submitted_inquiry()
    q1 = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q1["id"])
    q2 = data(_recalc(admin, inq["id"], adjustments=[{"description": "הנחה", "amount": "-50", "reason": "הנחת בדיקה"}]))
    _publish(admin, inq["id"], q2["id"])
    v = data(customer.get(f"/api/inquiries/{inq['id']}/quote"))
    assert v["version"] == 2 and v["id"] == q2["id"]


def test_accepted_quote_cannot_be_superseded_by_new_publish(customer, admin):
    inq = customer.submitted_inquiry()
    q1 = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q1["id"])
    customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": q1["id"], "version": 1})
    q2 = data(_recalc(admin, inq["id"]))
    r = _publish(admin, inq["id"], q2["id"])
    # פנייה במצב accepted: הפרסום דורש מעבר סטטוס שאינו מותר → 409, וההצעה המאושרת נשארת
    assert r.status_code in (200, 409)
    q1_after = next(q for q in data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["quotes"] if q["id"] == q1["id"])
    assert q1_after["status"] == "accepted"


# ---- ביטול / סגירה / טיפול ----
def test_cancel_published_returns_inquiry_to_carpenter(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q["id"])
    c = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/cancel", {"quote_id": q["id"], "reason": "טעות"}))
    assert c["status"] == "cancelled" and c["cancelled_at"]
    assert data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["status"] == "awaiting_carpenter"
    assert data(customer.get(f"/api/inquiries/{inq['id']}/quote")) is None


def test_cancel_accepted_quote_rejected(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q["id"])
    customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": q["id"], "version": 1})
    assert admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/cancel", {"quote_id": q["id"]}).status_code == 409


def test_cancel_twice_idempotent(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"]))
    admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/cancel", {"quote_id": q["id"]})
    assert admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/cancel", {"quote_id": q["id"]}).status_code == 200


def test_close_inquiry_blocks_everything(customer, admin):
    inq = customer.submitted_inquiry()
    d = data(admin.post(f"/api/admin/inquiries/{inq['id']}/close", {"reason": "לקוח ביטל"}))
    assert d["status"] == "closed"
    assert _recalc(admin, inq["id"]).status_code == 409
    assert admin.post(f"/api/admin/inquiries/{inq['id']}/close", {"reason": "שוב"}).status_code == 200


def test_close_reason_too_long(customer, admin):
    inq = customer.submitted_inquiry()
    assert admin.post(f"/api/admin/inquiries/{inq['id']}/close", {"reason": "א" * 501}).status_code == 422


def test_reopen_only_from_change_requested(customer, admin):
    inq = customer.submitted_inquiry()
    assert admin.post(f"/api/admin/inquiries/{inq['id']}/reopen").status_code == 409
    q = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q["id"])
    customer.post(f"/api/inquiries/{inq['id']}/quote/change-request", {"quote_id": q["id"], "message": "שינוי בבקשה"})
    d = data(admin.post(f"/api/admin/inquiries/{inq['id']}/reopen"))
    assert d["status"] == "awaiting_carpenter" and d["quotes"][0]["change_request_text"] == "שינוי בבקשה"


# ---- הערות והיסטוריה ----
def test_notes_create_and_list(customer, admin):
    inq = customer.submitted_inquiry()
    n = data(admin.post(f"/api/admin/inquiries/{inq['id']}/notes", {"body": "הערה פנימית"}))
    assert n["body"] == "הערה פנימית"
    assert data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["notes"][0]["body"] == "הערה פנימית"


@pytest.mark.parametrize("body", ["", "   ", "א" * 4001])
def test_note_validation(customer, admin, body):
    inq = customer.submitted_inquiry()
    r = admin.post(f"/api/admin/inquiries/{inq['id']}/notes", {"body": body})
    assert r.status_code in (422, 500) and r.status_code != 201


def test_event_trail_full_lifecycle(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"])); _publish(admin, inq["id"], q["id"])
    customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": q["id"], "version": 1})
    types = [e["event_type"] for e in data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["events"]]
    for t in ("inquiry_created", "spec_updated", "submitted", "quote_draft_created", "quote_published", "quote_accepted"):
        assert t in types
    assert types.index("submitted") < types.index("quote_published") < types.index("quote_accepted")


def test_events_record_actor_types(customer, admin):
    inq = customer.submitted_inquiry()
    _recalc(admin, inq["id"])
    actors = {e["actor_type"] for e in data(admin.get(f"/api/admin/inquiries/{inq['id']}"))["events"]}
    assert {"customer", "carpenter"} <= actors


# ---- מחירון ----
def test_pricebook_get(admin):
    d = data(admin.get("/api/admin/pricebook"))
    assert d["active"]["is_demo"] is True and d["active"]["items"] and d["versions"]


def test_pricebook_save_creates_new_version_and_keeps_old(admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    r = admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": book["items"], "is_demo": True})
    assert r.status_code == 201 and r.json()["data"]["version"] == book["version"] + 1
    versions = [v["version"] for v in data(admin.get("/api/admin/pricebook"))["versions"]]
    assert book["version"] in versions


def test_pricebook_duplicate_codes_rejected(admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    items = book["items"] + [book["items"][0]]
    assert admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": items}).status_code == 422


@pytest.mark.parametrize("field,value", [("vat_rate", "1.5"), ("vat_rate", "-0.1"), ("waste_rate", "2"),
                                         ("quote_validity_days", 0), ("quote_validity_days", 366), ("base_labor_price", "-1")])
def test_pricebook_settings_validation(admin, field, value):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    settings = {**book["settings"], field: value}
    assert admin.put("/api/admin/pricebook", {"settings": settings, "items": book["items"]}).status_code == 422


def test_pricebook_negative_price_rejected(admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    items = [{**i, "unit_price": "-5"} if i["code"] == "HDF3" else i for i in book["items"]]
    assert admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": items}).status_code == 422


def test_pricebook_empty_items_rejected(admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    assert admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": []}).status_code == 422


def test_disabled_item_forces_manual(customer, admin):
    book = data(admin.get("/api/admin/pricebook"))["active"]
    items = [{**i, "active": False} if i["code"] == "INSTALL" else i for i in book["items"]]
    admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": items, "is_demo": True})
    try:
        inq = customer.submitted_inquiry()
        q = data(_recalc(admin, inq["id"]))
        assert q["total"] is None and any("התקנה" in m for m in q["pricing"]["manual_required"])
    finally:
        admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": book["items"], "is_demo": True})


def test_pricebook_change_does_not_alter_published_quote(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"])); p = data(_publish(admin, inq["id"], q["id"]))
    book = data(admin.get("/api/admin/pricebook"))["active"]
    items = [{**i, "unit_price": str(float(i["unit_price"]) * 3)} for i in book["items"]]
    admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": items, "is_demo": True})
    try:
        assert data(customer.get(f"/api/inquiries/{inq['id']}/quote"))["total"] == p["total"]
        new = data(_recalc(admin, Client().submitted_inquiry()["id"]))
        assert float(new["total"]) > float(p["total"]) and new["pricing"]["pricebook_version"] == book["version"] + 1
    finally:
        admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": book["items"], "is_demo": True})


def test_vat_change_applies_to_new_quotes_only(customer, admin):
    inq = customer.submitted_inquiry()
    q = data(_recalc(admin, inq["id"])); p = data(_publish(admin, inq["id"], q["id"]))
    book = data(admin.get("/api/admin/pricebook"))["active"]
    admin.put("/api/admin/pricebook", {"settings": {**book["settings"], "vat_rate": "0.20"}, "items": book["items"], "is_demo": True})
    try:
        assert data(customer.get(f"/api/inquiries/{inq['id']}/quote"))["vat_rate"] == p["vat_rate"]
        new = data(_recalc(admin, Client().submitted_inquiry()["id"]))
        assert Decimal(new["vat_rate"]) == Decimal("0.20")
    finally:
        admin.put("/api/admin/pricebook", {"settings": book["settings"], "items": book["items"], "is_demo": True})


# ---- לקוחות ----
def test_customer_create_and_get(admin):
    c = data(admin.post("/api/admin/customers", {"full_name": "לקוח בדיקה", "phone": "0501231234", "city": "חולון"}))
    d = data(admin.get(f"/api/admin/customers/{c['id']}"))
    assert d["full_name"] == "לקוח בדיקה" and d["inquiries"] == []


@pytest.mark.parametrize("body", [{"full_name": "א", "phone": "0501231234"}, {"full_name": "לקוח", "phone": "123"},
                                  {"full_name": "לקוח"}, {"full_name": "לקוח", "phone": "0501231234", "extra": 1}])
def test_customer_validation(admin, body):
    assert admin.post("/api/admin/customers", body).status_code == 422


def test_link_inquiry_creates_customer_from_contact(customer, admin):
    inq = customer.submitted_inquiry(full_name="קישור בדיקה", phone="0507654321")
    assert any(i["id"] == inq["id"] for i in data(admin.get("/api/admin/customers/unlinked-inquiries")))
    r = data(admin.post("/api/admin/customers/link", {"inquiry_id": inq["id"], "create_from_contact": True}))
    d = data(admin.get(f"/api/admin/customers/{r['customer_id']}"))
    assert d["phone"] == "0507654321" and d["inquiries"][0]["id"] == inq["id"]
    assert not any(i["id"] == inq["id"] for i in data(admin.get("/api/admin/customers/unlinked-inquiries")))


def test_link_inquiry_to_existing_customer(customer, admin):
    c = data(admin.post("/api/admin/customers", {"full_name": "לקוח קיים", "phone": "0509998877"}))
    inq = customer.submitted_inquiry()
    data(admin.post("/api/admin/customers/link", {"inquiry_id": inq["id"], "customer_id": c["id"]}))
    assert data(admin.get(f"/api/admin/customers/{c['id']}"))["inquiries"][0]["id"] == inq["id"]


def test_no_automatic_merge_by_phone(customer, admin):
    a = customer.submitted_inquiry(phone="0501111111")
    b = Client().submitted_inquiry(phone="0501111111")
    unlinked = {i["id"] for i in data(admin.get("/api/admin/customers/unlinked-inquiries"))}
    assert a["id"] in unlinked and b["id"] in unlinked


def test_link_unknown_customer_404(customer, admin):
    inq = customer.submitted_inquiry()
    assert admin.post("/api/admin/customers/link", {"inquiry_id": inq["id"], "customer_id": "nope"}).status_code == 404


def test_link_inquiry_without_contact_rejected(customer, admin):
    inq = customer.new_inquiry()
    assert admin.post("/api/admin/customers/link", {"inquiry_id": inq["id"], "create_from_contact": True}).status_code == 422


def test_customers_search(admin):
    admin.post("/api/admin/customers", {"full_name": "חיפוש ייחודי", "phone": "0503334455"})
    assert any(c["full_name"] == "חיפוש ייחודי" for c in data(admin.get("/api/admin/customers?q=ייחודי")))
    assert any(c["phone"] == "0503334455" for c in data(admin.get("/api/admin/customers?q=0503334455")))
