"""תשתית, proxy, קבצים סטטיים, אבטחת בקשות."""
import pytest
import requests

from .conftest import BASE, Client, data


# ---- תשתית ו-proxy ----
@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_health_endpoints(customer, path):
    r = customer.get(path)
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_api_health_reports_demo_mode(customer):
    j = customer.get("/api/health").json()
    assert j["demo_mode"] is True and j["ai"] == "simulated" and j["database"] == "sqlite"


@pytest.mark.parametrize("page", ["/", "/index.html", "/chat.html", "/summary.html", "/track.html", "/quote.html",
                                  "/admin/login.html", "/admin/dashboard.html", "/admin/inquiry.html",
                                  "/admin/pricebook.html", "/admin/customers.html"])
def test_static_pages_served_rtl(customer, page):
    r = customer.get(page)
    assert r.status_code == 200 and 'dir="rtl"' in r.text and 'lang="he"' in r.text


@pytest.mark.parametrize("asset", ["/css/base.css", "/css/customer.css", "/css/admin.css", "/js/api.js", "/js/ui.js",
                                   "/js/spec-card.js", "/js/spec-view.js", "/js/admin/auth.js", "/img/hero-wardrobe.webp"])
def test_static_assets(customer, asset):
    assert customer.get(asset).status_code == 200


def test_config_js_has_no_secrets(customer):
    body = customer.get("/config.js").text
    assert "window.APP_CONFIG" in body and "service_role" not in body and "sk-" not in body


def test_404_page(customer):
    r = customer.get("/does-not-exist.html")
    assert r.status_code == 404 and "העמוד לא נמצא" in r.text


def test_api_unknown_route_json_404(customer):
    r = customer.get("/api/nope")
    assert r.status_code == 404 and r.json()["success"] is False


def test_security_headers_present(customer):
    h = customer.get("/api/health").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer" and "no-store" in h["Cache-Control"]


def test_static_headers_present(customer):
    h = customer.get("/css/base.css").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"


def test_csrf_cookie_is_set_on_first_request():
    s = requests.Session()
    s.get(BASE + "/api/health")
    assert s.cookies.get("csrf_token")


def test_session_cookie_httponly_after_inquiry(customer):
    customer.new_inquiry()
    cookie = next(c for c in customer.s.cookies if c.name == "aron_session")
    assert cookie.has_nonstandard_attr("HttpOnly") or "httponly" in str(cookie._rest).lower()


# ---- CSRF / Origin ----
def test_post_without_csrf_header_rejected():
    s = requests.Session(); s.get(BASE + "/api/health")
    r = s.post(BASE + "/api/inquiries", json={}, headers={"Origin": BASE})
    assert r.status_code == 403


def test_post_with_wrong_csrf_header_rejected():
    s = requests.Session(); s.get(BASE + "/api/health")
    r = s.post(BASE + "/api/inquiries", json={}, headers={"Origin": BASE, "X-CSRF-Token": "wrong"})
    assert r.status_code == 403


def test_post_without_csrf_cookie_rejected():
    r = requests.post(BASE + "/api/inquiries", json={}, headers={"Origin": BASE, "X-CSRF-Token": "x"})
    assert r.status_code == 403


def test_wrong_origin_rejected(customer):
    r = customer.post("/api/inquiries", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_get_does_not_require_csrf():
    s = requests.Session()
    assert s.get(BASE + "/api/catalog").status_code == 200


# ---- גדלים וקלט ----
def test_oversized_body_rejected(customer):
    inq = customer.new_inquiry()
    r = customer.chat(inq["id"], "א" * 40000, 1)
    assert r.status_code in (413, 422)


def test_message_over_2000_chars_rejected(customer):
    inq = customer.new_inquiry()
    r = customer.chat(inq["id"], "א" * 2001, 1)
    assert r.status_code == 422


def test_message_exactly_2000_chars_accepted(customer):
    inq = customer.new_inquiry()
    r = customer.chat(inq["id"], "א" * 2000, 1)
    assert r.status_code == 200


def test_empty_message_rejected(customer):
    inq = customer.new_inquiry()
    assert customer.chat(inq["id"], "", 1).status_code == 422


def test_non_json_body_rejected(customer):
    inq = customer.new_inquiry()
    r = customer.req("POST", f"/api/inquiries/{inq['id']}/chat", data="not json",
                     headers={"Content-Type": "text/plain"})
    assert r.status_code in (415, 422)


def test_unknown_field_in_body_rejected(customer):
    inq = customer.new_inquiry()
    r = customer.post(f"/api/inquiries/{inq['id']}/chat", {"message": "x", "base_version": 1, "hack": True})
    assert r.status_code == 422


@pytest.mark.parametrize("payload", [{"expected_version": 1, "patch": {"width_cm": "<script>alert(1)</script>"}},
                                     {"expected_version": 1, "patch": {"color": "<img src=x onerror=alert(1)>"}}])
def test_html_in_input_is_stored_as_text_not_executed(customer, payload):
    inq = customer.new_inquiry()
    r = customer.patch(f"/api/inquiries/{inq['id']}/spec", payload)
    # רוחב חייב להיות מספר → 422; צבע נשמר כטקסט, אבל מוחזר כ-JSON ולא כ-HTML
    if "width_cm" in payload["patch"]:
        assert r.status_code == 422
    else:
        assert r.status_code == 200 and r.headers["Content-Type"].startswith("application/json")


# ---- הגבלת קצב ----
def test_rate_limit_after_20_chat_messages(customer):
    inq = customer.new_inquiry()
    codes = []
    version = 1
    for i in range(22):
        r = customer.chat(inq["id"], f"הודעה {i}", version)
        codes.append(r.status_code)
        if r.status_code == 200:
            version = r.json()["data"]["spec_version"]
    assert 429 in codes and codes.index(429) >= 20


# ---- הרשאות ניהול ----
@pytest.mark.parametrize("path", ["/api/admin/me", "/api/admin/dashboard", "/api/admin/inquiries",
                                  "/api/admin/pricebook", "/api/admin/customers"])
def test_admin_routes_require_token(customer, path):
    assert customer.get(path).status_code == 401


@pytest.mark.parametrize("header", ["Bearer garbage", "Bearer ", "Basic abc", "demo-carpenter-token",
                                    "Bearer " + "x" * 5000])
def test_admin_bad_tokens_rejected(customer, header):
    r = customer.get("/api/admin/me", headers={"Authorization": header})
    assert r.status_code == 401


def test_demo_token_accepted_in_demo(admin):
    me = data(admin.get("/api/admin/me"))
    assert me["demo_mode"] is True and me["display_name"]


def test_admin_post_requires_csrf_even_with_token():
    s = requests.Session(); s.get(BASE + "/api/health")
    r = s.post(BASE + "/api/admin/customers", json={"full_name": "x y", "phone": "0501234567"},
               headers={"Origin": BASE, "Authorization": "Bearer demo-carpenter-token"})
    assert r.status_code == 403
