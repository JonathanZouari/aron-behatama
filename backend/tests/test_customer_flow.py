"""תהליך לקוח מלא, בידוד פניות, גרסאות מול AI, שליחה כפולה, כשל AI."""
from app.schemas.agent_output import AgentOutput
from app.schemas.wardrobe_spec import SpecPatch

from .conftest import ADMIN, FULL_PATCH, create_submitted_inquiry, csrf, publish_quote


def test_full_flow_customer_to_acceptance(client):
    inquiry = create_submitted_inquiry(client)
    assert inquiry["status"] == "awaiting_carpenter"
    assert inquiry["spec"]["customer_confirmed"] is True

    # לפני פרסום — הלקוח לא רואה הצעה
    assert client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"] is None

    quote = publish_quote(client, inquiry["id"])
    assert quote["status"] == "published"

    visible = client.get(f"/api/inquiries/{inquiry['id']}/quote").get_json()["data"]
    assert visible["can_accept"] and visible["total"] == quote["total"]
    # אין חשיפת סיבות/הסברים פנימיים
    assert "reason" not in visible["items"][0]
    assert "pricing" not in visible

    headers = csrf(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                    json={"quote_id": visible["id"], "version": visible["version"]}, headers=headers)
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "accepted"
    # אישור חוזר — idempotent, ללא שגיאה וללא כפילות
    r2 = client.post(f"/api/inquiries/{inquiry['id']}/quote/accept",
                     json={"quote_id": visible["id"], "version": visible["version"]}, headers=headers)
    assert r2.status_code == 200
    detail = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]
    assert detail["status"] == "accepted"
    assert sum(1 for e in detail["events"] if e["event_type"] == "quote_accepted") == 1


def test_chat_extracts_and_converts_units(client):
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    r = client.post(f"/api/inquiries/{inquiry['id']}/chat",
                    json={"message": "ארון ברוחב 2.4 מטר, גובה 2600 מ״מ, 3 דלתות, בלי מגירות", "base_version": 1},
                    headers=headers)
    data = r.get_json()["data"]
    assert data["simulated"] is True
    assert data["spec"]["width_cm"] == 240 and data["spec"]["height_cm"] == 260
    assert data["spec"]["doors"] == 3 and data["spec"]["internal_drawers"] == 0
    assert data["spec_version"] == 2
    assert "depth_cm" in data["missing_fields"]


def test_ambiguous_phrase_asks_for_clarification(client):
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    r = client.post(f"/api/inquiries/{inquiry['id']}/chat",
                    json={"message": "אני רוצה ארון שניים על שלוש", "base_version": 1}, headers=headers)
    data = r.get_json()["data"]
    assert data["clarification_needed"] is True
    assert data["spec"]["width_cm"] is None and data["spec_version"] == 1


def test_stale_ai_reply_cannot_overwrite_newer_form_change(client):
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    # הטופס מעדכן לגרסה 2
    client.patch(f"/api/inquiries/{inquiry['id']}/spec",
                 json={"expected_version": 1, "patch": {"width_cm": 200}}, headers=headers)
    # תשובת AI שהתבססה על גרסה 1 נדחית
    r = client.post(f"/api/inquiries/{inquiry['id']}/chat",
                    json={"message": "רוחב 300 ס״מ", "base_version": 1}, headers=headers)
    assert r.status_code == 409
    spec = client.get(f"/api/inquiries/{inquiry['id']}").get_json()["data"]["spec"]
    assert spec["spec"]["width_cm"] == 200


def test_customer_cannot_access_other_inquiry(client, app):
    first = create_submitted_inquiry(client)
    other = app.test_client()
    r = other.get(f"/api/inquiries/{first['id']}")
    assert r.status_code == 404
    r = other.get(f"/api/inquiries/{first['id']}/quote")
    assert r.status_code == 404


def test_access_link_grants_session_and_is_hashed(client, app, container):
    inquiry = create_submitted_inquiry(client)
    r = client.post(f"/api/inquiries/{inquiry['id']}/access-link", headers=csrf(client))
    path = r.get_json()["data"]["path"]
    token = path.rsplit("/", 1)[1]
    rows = container.db.fetch_all("select token_hash from customer_access_tokens")
    assert rows and rows[0]["token_hash"] != token and len(rows[0]["token_hash"]) == 64

    fresh = app.test_client()
    redirect = fresh.get(path)
    assert redirect.status_code == 302 and "token" not in redirect.headers["Location"]
    assert fresh.get(f"/api/inquiries/{inquiry['id']}").status_code == 200
    # קישור לא תקין
    assert "error=invalid_link" in app.test_client().get("/api/access/not-a-real-token").headers["Location"]


def test_double_submit_is_idempotent(client):
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    spec = client.patch(f"/api/inquiries/{inquiry['id']}/spec",
                        json={"expected_version": 1, "patch": FULL_PATCH}, headers=headers).get_json()["data"]
    body = {"spec_version": spec["version"], "confirmed": True, "full_name": "דנה", "phone": "0521234567"}
    a = client.post(f"/api/inquiries/{inquiry['id']}/submit", json=body, headers=headers)
    b = client.post(f"/api/inquiries/{inquiry['id']}/submit", json=body, headers=headers)
    assert a.status_code == 200 and b.status_code == 200
    assert a.get_json()["data"]["number"] == b.get_json()["data"]["number"]
    events = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]["events"]
    assert sum(1 for e in events if e["event_type"] == "submitted") == 1


def test_incomplete_spec_goes_to_manual_review(client):
    partial = {"width_cm": 200, "height_cm": 240, "doors": 2, "delivery": False, "installation": False}
    inquiry = create_submitted_inquiry(client, patch=partial)
    assert inquiry["status"] == "awaiting_carpenter"
    assert inquiry["requires_manual_review"] is True
    detail = client.get(f"/api/admin/inquiries/{inquiry['id']}", headers=ADMIN).get_json()["data"]
    assert any("חסר" in r for r in detail["manual_review_reasons"])
    # ניסיון פרסום נחסם — אין מחיר סופי
    headers = {**ADMIN, **csrf(client)}
    draft = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/recalculate",
                        json={"adjustments": []}, headers=headers).get_json()["data"]
    assert draft["total"] is None
    pub = client.post(f"/api/admin/inquiries/{inquiry['id']}/quotes/publish", json={"quote_id": draft["id"]},
                      headers=headers)
    assert pub.status_code == 409


def test_ai_failure_returns_503_and_form_still_works(client, container):
    class Broken:
        def run(self, *a, **k):
            raise RuntimeError("boom")

    container.inquiry_service.agent = Broken()
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    r = client.post(f"/api/inquiries/{inquiry['id']}/chat", json={"message": "שלום", "base_version": 1},
                    headers=headers)
    assert r.status_code == 503 and r.get_json()["ai_unavailable"] is True
    r = client.patch(f"/api/inquiries/{inquiry['id']}/spec",
                     json={"expected_version": 1, "patch": {"width_cm": 200}}, headers=headers)
    assert r.status_code == 200 and r.get_json()["data"]["spec"]["width_cm"] == 200


def test_invalid_ai_output_is_rejected(client, container):
    class Weird:
        def run(self, *a, **k):
            # פלט שאינו תואם לסכמה (רוחב שלילי) — חייב להיכשל באימות בשרת
            return AgentOutput(reply="ok", proposed_spec_patch=SpecPatch.model_construct(width_cm=-5))

    container.inquiry_service.agent = Weird()
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    r = client.post(f"/api/inquiries/{inquiry['id']}/chat", json={"message": "היי", "base_version": 1},
                    headers=headers)
    assert r.status_code == 503


def test_csrf_required_for_state_changes(client):
    client.get("/health")
    r = client.post("/api/inquiries")  # ללא כותרת CSRF
    assert r.status_code == 403


def test_rate_limit_on_chat(client, container):
    container.ai_limiter.limit = 2
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    codes = []
    for _ in range(3):
        r = client.post(f"/api/inquiries/{inquiry['id']}/chat", json={"message": "שלום", "base_version": 1},
                        headers=headers)
        codes.append(r.status_code)
    assert codes[-1] == 429
