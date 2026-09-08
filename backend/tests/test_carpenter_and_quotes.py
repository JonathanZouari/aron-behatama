"""הרשאות נגר, גרסאות הצעה, תפוגה, בקשת שינוי, מחירון היסטורי, אי-חשיפה."""
from datetime import timedelta

from app.repositories.db import utcnow

from .conftest import ADMIN, create_submitted_inquiry, csrf, publish_quote


def test_admin_routes_require_carpenter(client):
    assert client.get("/api/admin/inquiries").status_code == 401
    assert client.get("/api/admin/inquiries", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401
    assert client.get("/api/admin/inquiries", headers=ADMIN).status_code == 200


def test_demo_login_blocked_in_production(container):
    from app.config import ConfigError, load_settings

    try:
        load_settings({"APP_ENV": "production", "DEMO_MODE": "true", "SESSION_SECRET": "x" * 40})
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_internal_notes_and_drafts_not_exposed_to_customer(client):
    inquiry = create_submitted_inquiry(client)
    headers = {**ADMIN, **csrf(client)}
    client.post(f"/api/admin/inquiries/{inquiry['id']}/notes", json={"body": "הערה סודית"}, headers=headers)
    client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate", json={"adjustments": []}, headers=headers)
    raw = client.get(f"/api/inquiries/{inquiry['id']}").get_data(as_text=True)
    assert "הערה סודית" not in raw and '"notes"' not in raw and "internal_notes" not in raw
    assert client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"] is None  # טיוטה אינה נראית


def test_new_version_supersedes_previous_and_only_exact_version_accepts(client):
    inquiry = create_submitted_inquiry(client)
    v1 = publish_quote(client, inquiry["id"])
    # שינוי מפרט על ידי הנגר → טיוטה חדשה → פרסום v2
    headers = {**ADMIN, **csrf(client)}
    detail = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]
    r = client.patch(f"/api/admin/inquiries/{inquiry['id']}/spec",
                     json={"expected_version": detail["spec"]["version"], "patch": {"shelves": 8}}, headers=headers)
    assert r.status_code == 200
    v2 = publish_quote(client, inquiry["id"])
    assert v2["version"] == 2

    quotes = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]["quotes"]
    assert {q["version"]: q["status"] for q in quotes} == {1: "superseded", 2: "published"}

    # הלקוח רואה את v2 עם הדגשת ההבדל, ואינו יכול לאשר את v1
    visible = client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"]
    assert visible["version"] == 2 and visible["spec_changes"]["shelves"] == {"before": 6, "after": 8}
    c = csrf(client)
    bad = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept", json={"quote_id": v1["id"], "version": 1},
                      headers=c)
    assert bad.status_code == 409
    wrong_version = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                                json={"quote_id": v2["id"], "version": 1}, headers=c)
    assert wrong_version.status_code == 409
    good = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept", json={"quote_id": v2["id"], "version": 2},
                       headers=c)
    assert good.status_code == 200


def test_spec_change_marks_draft_stale_and_blocks_publish(client):
    inquiry = create_submitted_inquiry(client)
    headers = {**ADMIN, **csrf(client)}
    draft = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate", json={"adjustments": []},
                        headers=headers).get_json()["data"]
    detail = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]
    client.patch(f"/api/admin/inquiries/{inquiry['id']}/spec",
                 json={"expected_version": detail["spec"]["version"], "patch": {"doors": 5}}, headers=headers)
    pub = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/publish", json={"quote_id": draft["id"]},
                      headers=headers)
    assert pub.status_code == 409 and "לחשב מחדש" in pub.get_json()["error"]


def test_expired_quote_cannot_be_accepted(client, container):
    inquiry = create_submitted_inquiry(client)
    quote = publish_quote(client, inquiry["id"])
    container.db.execute("update quotes set expires_at = ? where id = ?", (utcnow() - timedelta(days=1), quote["id"]))
    visible = client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"]
    assert visible["status"] == "expired" and visible["can_accept"] is False
    r = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                    json={"quote_id": quote["id"], "version": quote["version"]}, headers=csrf(client))
    assert r.status_code == 409


def test_change_request_blocks_acceptance_until_carpenter_handles(client):
    inquiry = create_submitted_inquiry(client)
    quote = publish_quote(client, inquiry["id"])
    c = csrf(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/quote/change-request",
                    json={"quote_id": quote["id"], "message": "אפשר צבע אגוז?"}, headers=c)
    assert r.status_code == 200 and r.get_json()["data"]["can_accept"] is False
    assert client.get(f"/api/inquiries/{inquiry['id']}").get_json()["data"]["status"] == "change_requested"
    blocked = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                          json={"quote_id": quote["id"], "version": quote["version"]}, headers=c)
    assert blocked.status_code == 409
    # הנגר מפרסם גרסה חדשה — ניתן לאשר אותה
    v2 = publish_quote(client, inquiry["id"])
    ok = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                     json={"quote_id": v2["id"], "version": v2["version"]}, headers=c)
    assert ok.status_code == 200


def test_pricebook_update_does_not_change_existing_quote(client):
    inquiry = create_submitted_inquiry(client)
    quote = publish_quote(client, inquiry["id"])
    headers = {**ADMIN, **csrf(client)}
    book = client.get("/api/admin/pricebook", headers=ADMIN).get_json()["data"]["active"]
    items = [{**i, "unit_price": str(float(i["unit_price"]) * 2)} for i in book["items"]]
    r = client.put("/api/admin/pricebook", json={"settings": book["settings"], "items": items, "is_demo": True},
                   headers=headers)
    assert r.status_code == 201 and r.get_json()["data"]["version"] == book["version"] + 1
    same = client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"]
    assert same["total"] == quote["total"]
    # הצעה חדשה מחושבת לפי המחירון החדש ושומרת את גרסת המחירון
    inquiry2 = create_submitted_inquiry(client)
    quote2 = publish_quote(client, inquiry2["id"])
    assert quote2["pricing"]["pricebook_version"] == book["version"] + 1
    assert float(quote2["total"]) > float(quote["total"])


def test_manual_adjustment_requires_reason_and_manual_handled_gate(client):
    partial = {"width_cm": 200, "height_cm": 240, "depth_cm": 60, "body_material_id": "SANDWICH17",
               "front_material_id": "MDF_COATED", "finish_id": "FIN_OAK_LIGHT", "doors": 2, "internal_drawers": 0,
               "shelves": 3, "compartments": 1, "soft_close": False, "delivery": True, "installation": False,
               "city": "אילת"}  # אין אזור הובלה לאילת → תמחור ידני
    inquiry = create_submitted_inquiry(client, patch=partial, contact={"city": "אילת"})
    headers = {**ADMIN, **csrf(client)}
    bad = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate",
                      json={"adjustments": [{"description": "הובלה לאילת", "amount": "900", "reason": ""}]},
                      headers=headers)
    assert bad.status_code == 422
    draft = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate",
                        json={"adjustments": [{"description": "הובלה לאילת", "amount": "900",
                                               "reason": "מחיר הובלה מיוחד לדרום הרחוק"}]},
                        headers=headers).get_json()["data"]
    assert draft["total"] is None and any("הובלה" in m for m in draft["pricing"]["manual_required"])
    pub = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/publish", json={"quote_id": draft["id"]},
                      headers=headers)
    assert pub.status_code == 409


def test_status_transitions_enforced(client):
    inquiry = create_submitted_inquiry(client)
    headers = {**ADMIN, **csrf(client)}
    closed = client.post(f"/api/admin/inquiries/{inquiry['id']}/close", json={"reason": "בדיקה"}, headers=headers)
    assert closed.status_code == 200 and closed.get_json()["data"]["status"] == "closed"
    # אין פרסום/חישוב לפנייה סגורה
    r = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate", json={"adjustments": []},
                    headers=headers)
    assert r.status_code == 409


def test_customer_link_is_explicit(client):
    inquiry = create_submitted_inquiry(client)
    headers = {**ADMIN, **csrf(client)}
    unlinked = client.get("/api/admin/customers/unlinked-inquiries", headers=ADMIN).get_json()["data"]
    assert any(i["id"] == inquiry["id"] for i in unlinked)
    r = client.post("/api/admin/customers/link", json={"inquiry_id": inquiry["id"], "create_from_contact": True},
                    headers=headers)
    assert r.status_code == 200
    customer_id = r.get_json()["data"]["customer_id"]
    detail = client.get(f"/api/admin/customers/{customer_id}", headers=ADMIN).get_json()["data"]
    assert detail["inquiries"][0]["id"] == inquiry["id"]
