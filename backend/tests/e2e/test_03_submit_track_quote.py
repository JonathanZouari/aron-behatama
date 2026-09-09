"""שליחה לנגר, מעקב, קישורי גישה, הצעה ללקוח, אישור ובקשת שינוי."""
import concurrent.futures as cf

import pytest

from .conftest import BASE, FULL, Client, data


# ---- שליחה: ולידציית פרטי קשר ----
@pytest.mark.parametrize("field,value,ok", [
    ("phone", "0521234567", True), ("phone", "052-1234567", True), ("phone", "+972521234567", True),
    ("phone", "052 123 4567", True), ("phone", "12345", False), ("phone", "abcdefghij", False), ("phone", "", False),
    ("phone", "0" * 30, False),
    ("full_name", "א", False), ("full_name", "אב", True), ("full_name", "א" * 120, True), ("full_name", "א" * 121, False),
    ("full_name", "   ", False),
    ("email", "dana@example.com", True), ("email", "not-an-email", False), ("email", "", True), ("email", None, True),
])
def test_contact_validation(customer, field, value, ok):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, FULL)
    r = customer.submit(inq, s["version"], **{field: value})
    assert (r.status_code == 200) is ok, r.text
    if not ok and r.status_code == 422 and field != "full_name" or (not ok and field == "full_name" and value != "   "):
        pass


def test_submit_requires_explicit_confirmation(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, FULL)
    r = customer.submit(inq, s["version"], confirmed=False)
    assert r.status_code == 422


def test_submit_requires_city_when_delivery(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, {**FULL, "city": None})
    r = customer.submit(inq, s["version"])
    assert r.status_code == 422 and "city" in r.json()["errors"]


def test_submit_city_from_form_fills_spec(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, {**FULL, "city": None})
    d = data(customer.submit(inq, s["version"], city="חיפה"))
    assert d["spec"]["spec"]["city"] == "חיפה" and d["contact_city"] == "חיפה"


def test_submit_without_city_when_no_services(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, {**FULL, "delivery": False, "installation": False, "city": None})
    assert customer.submit(inq, s["version"]).status_code == 200


def test_submit_wrong_spec_version_409(customer):
    inq = customer.new_inquiry()
    customer.set_spec(inq, FULL)
    assert customer.submit(inq, 1).status_code == 409


def test_submit_twice_is_idempotent(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, FULL)
    a = data(customer.submit(inq, s["version"]))
    b = data(customer.submit(inq, s["version"]))
    assert a["number"] == b["number"] and b["status"] == "awaiting_carpenter"


def test_submit_marks_customer_confirmed_and_bumps_version(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, FULL)
    d = data(customer.submit(inq, s["version"]))
    assert d["spec"]["customer_confirmed"] is True and d["spec"]["version"] == s["version"] + 1


def test_submit_incomplete_spec_goes_to_manual(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, {"width_cm": 200, "height_cm": 200, "delivery": False, "installation": False})
    d = data(customer.submit(inq, s["version"]))
    assert d["status"] == "awaiting_carpenter" and d["requires_manual_review"] is True


def test_submit_empty_spec_allowed_to_manual(customer):
    inq = customer.new_inquiry()
    d = data(customer.submit(inq, 1))
    assert d["requires_manual_review"] is True


def test_public_view_has_no_internal_fields(customer):
    inq = customer.submitted_inquiry()
    raw = customer.get(f"/api/inquiries/{inq['id']}").text
    for forbidden in ("internal_notes", "row_version", "customer_id", "contact_phone", "\"notes\""):
        assert forbidden not in raw


def test_concurrent_submits_create_one_event(customer):
    inq = customer.new_inquiry()
    s = customer.set_spec(inq, FULL)
    with cf.ThreadPoolExecutor(5) as ex:
        codes = list(ex.map(lambda _: customer.submit(inq, s["version"]).status_code, range(5)))
    assert all(c in (200, 409) for c in codes) and 200 in codes
    events = data(Client(admin=True).get(f"/api/admin/inquiries/{inq['id']}"))["events"]
    assert sum(e["event_type"] == "submitted" for e in events) == 1


# ---- קישורי גישה ----
def test_access_link_grants_new_session(customer):
    inq = customer.submitted_inquiry()
    link = data(customer.post(f"/api/inquiries/{inq['id']}/access-link"))
    assert link["path"].startswith("/api/access/") and link["expires_at"]
    fresh = Client()
    r = fresh.s.get(BASE + link["path"], allow_redirects=False)
    assert r.status_code == 302 and "token" not in r.headers["Location"] and inq["id"] in r.headers["Location"]
    assert fresh.get(f"/api/inquiries/{inq['id']}").status_code == 200


def test_access_link_is_single_inquiry(customer):
    a = customer.submitted_inquiry()
    b = customer.submitted_inquiry()
    link = data(customer.post(f"/api/inquiries/{a['id']}/access-link"))
    fresh = Client(); fresh.s.get(BASE + link["path"])
    assert fresh.get(f"/api/inquiries/{a['id']}").status_code == 200
    assert fresh.get(f"/api/inquiries/{b['id']}").status_code == 404


def test_access_link_revocation(customer):
    inq = customer.submitted_inquiry()
    link = data(customer.post(f"/api/inquiries/{inq['id']}/access-link"))
    assert data(customer.post(f"/api/inquiries/{inq['id']}/access-link/revoke"))["revoked"] == 1
    r = Client().s.get(BASE + link["path"], allow_redirects=False)
    assert "invalid_link" in r.headers["Location"]


@pytest.mark.parametrize("token", ["", "x", "a" * 200, "../../etc/passwd", "%00", "'; DROP TABLE quotes;--"])
def test_invalid_access_tokens(token):
    r = Client().s.get(BASE + "/api/access/" + token, allow_redirects=False)
    assert r.status_code in (302, 404) and ("invalid_link" in r.headers.get("Location", "") or r.status_code == 404)


def test_access_link_only_by_owner(customer):
    inq = customer.submitted_inquiry()
    assert Client().post(f"/api/inquiries/{inq['id']}/access-link").status_code == 404


def test_multiple_links_all_valid(customer):
    inq = customer.submitted_inquiry()
    links = [data(customer.post(f"/api/inquiries/{inq['id']}/access-link"))["path"] for _ in range(3)]
    assert len(set(links)) == 3
    for p in links:
        c = Client(); c.s.get(BASE + p)
        assert c.get(f"/api/inquiries/{inq['id']}").status_code == 200


# ---- הצעה ללקוח ----
def test_no_quote_before_publish(customer, admin):
    inq = customer.submitted_inquiry()
    admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []})
    assert data(customer.get(f"/api/inquiries/{inq['id']}/quote")) is None
    assert data(customer.get(f"/api/inquiries/{inq['id']}"))["has_quote"] is False


def test_published_quote_visible_and_complete(published):
    customer, inq, quote = published
    q = data(customer.get(f"/api/inquiries/{inq['id']}/quote"))
    assert q["status"] == "published" and q["can_accept"] and q["total"] == quote["total"]
    assert q["subtotal"] and q["vat_amount"] and q["expires_at"] and q["terms_he"] and len(q["items"]) >= 8
    assert float(q["total"]) == round(float(q["subtotal"]) + float(q["vat_amount"]), 2)


def test_public_quote_hides_internal_reasons(published):
    customer, inq, _ = published
    raw = customer.get(f"/api/inquiries/{inq['id']}/quote").text
    assert '"reason"' not in raw and "pricing_snapshot" not in raw and "manual_handled" not in raw


def test_accept_quote(published):
    customer, inq, quote = published
    d = data(customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": quote["id"], "version": quote["version"]}))
    assert d["status"] == "accepted" and d["accepted_at"] and d["can_accept"] is False
    assert data(customer.get(f"/api/inquiries/{inq['id']}"))["status"] == "accepted"


def test_accept_twice_idempotent(published):
    customer, inq, quote = published
    body = {"quote_id": quote["id"], "version": quote["version"]}
    customer.post(f"/api/inquiries/{inq['id']}/quote/accept", body)
    assert customer.post(f"/api/inquiries/{inq['id']}/quote/accept", body).status_code == 200


def test_accept_wrong_version_409(published):
    customer, inq, quote = published
    r = customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": quote["id"], "version": 99})
    assert r.status_code == 409


def test_accept_unknown_quote_404(published):
    customer, inq, _ = published
    r = customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": "nope", "version": 1})
    assert r.status_code == 404


def test_accept_other_inquirys_quote_rejected(published, admin):
    customer, inq, quote = published
    other = Client(); other_inq = other.submitted_inquiry()
    r = other.post(f"/api/inquiries/{other_inq['id']}/quote/accept", {"quote_id": quote["id"], "version": 1})
    assert r.status_code == 404


def test_concurrent_accept_single_event(published):
    customer, inq, quote = published
    body = {"quote_id": quote["id"], "version": quote["version"]}
    with cf.ThreadPoolExecutor(5) as ex:
        codes = list(ex.map(lambda _: customer.post(f"/api/inquiries/{inq['id']}/quote/accept", body).status_code, range(5)))
    assert 200 in codes and all(c in (200, 409) for c in codes)
    events = data(Client(admin=True).get(f"/api/admin/inquiries/{inq['id']}"))["events"]
    assert sum(e["event_type"] == "quote_accepted" for e in events) == 1


def test_change_request_blocks_accept(published):
    customer, inq, quote = published
    d = data(customer.post(f"/api/inquiries/{inq['id']}/quote/change-request", {"quote_id": quote["id"], "message": "אפשר אגוז?"}))
    assert d["change_requested"] is True and d["can_accept"] is False
    assert data(customer.get(f"/api/inquiries/{inq['id']}"))["status"] == "change_requested"
    r = customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": quote["id"], "version": quote["version"]})
    assert r.status_code == 409


@pytest.mark.parametrize("msg", ["", "אב", "א" * 2001])
def test_change_request_message_validation(published, msg):
    customer, inq, quote = published
    r = customer.post(f"/api/inquiries/{inq['id']}/quote/change-request", {"quote_id": quote["id"], "message": msg})
    assert r.status_code == 422


def test_change_request_after_accept_rejected(published):
    customer, inq, quote = published
    customer.post(f"/api/inquiries/{inq['id']}/quote/accept", {"quote_id": quote["id"], "version": quote["version"]})
    r = customer.post(f"/api/inquiries/{inq['id']}/quote/change-request", {"quote_id": quote["id"], "message": "עוד משהו"})
    assert r.status_code == 409


def test_quote_hidden_from_other_session(published):
    _, inq, _ = published
    assert Client().get(f"/api/inquiries/{inq['id']}/quote").status_code == 404
