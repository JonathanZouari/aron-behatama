"""E2E מול המערכת המקומית המלאה: דפדפן-דמה (requests) → Frontend proxy (3000) → Backend (5000) → SQLite.

הרצה:  cd backend && pytest tests/e2e -q      (דורש: frontend + backend רצים בדמו)
משתנה: E2E_BASE (ברירת מחדל http://localhost:3000)
"""
import os
import pytest
import requests

BASE = os.environ.get("E2E_BASE", "http://localhost:3000")
ADMIN_TOKEN = "demo-carpenter-token"

FULL = {"width_cm": 240, "height_cm": 260, "depth_cm": 60, "body_material_id": "SANDWICH17",
        "front_material_id": "MDF_COATED", "finish_id": "FIN_OAK_LIGHT", "doors": 4, "internal_drawers": 2,
        "shelves": 6, "compartments": 2, "soft_close": True, "delivery": True, "installation": True, "city": "תל אביב"}
CONTACT = {"confirmed": True, "full_name": "דנה לוי", "phone": "0521234567"}


class Client:
    """לקוח HTTP שמתנהג כמו דפדפן: cookies, Origin, כותרת CSRF."""

    def __init__(self, admin: bool = False):
        self.s = requests.Session()
        self.s.headers["Origin"] = BASE
        self.s.get(BASE + "/api/health", timeout=30)
        self.s.headers["X-CSRF-Token"] = self.s.cookies.get("csrf_token") or ""
        if admin:
            self.s.headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"

    def req(self, method, path, **kw):
        kw.setdefault("timeout", 60)
        return self.s.request(method, BASE + path, **kw)

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.req("POST", path, json=json if json is not None else {}, **kw)

    def patch(self, path, json, **kw):
        return self.req("PATCH", path, json=json, **kw)

    def put(self, path, json, **kw):
        return self.req("PUT", path, json=json, **kw)

    # ---- זרימות מקוצרות ----
    def new_inquiry(self) -> dict:
        r = self.post("/api/inquiries")
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def set_spec(self, inquiry, patch, expected_version=None) -> dict:
        version = expected_version or inquiry["spec"]["version"]
        r = self.patch(f"/api/inquiries/{inquiry['id']}/spec", {"expected_version": version, "patch": patch})
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def submit(self, inquiry, spec_version, **contact) -> requests.Response:
        body = {**CONTACT, "spec_version": spec_version, **contact}
        return self.post(f"/api/inquiries/{inquiry['id']}/submit", body)

    def submitted_inquiry(self, patch=None, **contact) -> dict:
        inq = self.new_inquiry()
        spec = self.set_spec(inq, patch or FULL)
        r = self.submit(inq, spec["version"], **contact)
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def chat(self, inquiry_id, message, base_version) -> requests.Response:
        return self.post(f"/api/inquiries/{inquiry_id}/chat", {"message": message, "base_version": base_version})


def data(r: requests.Response):
    assert r.status_code < 300, f"{r.status_code}: {r.text[:300]}"
    return r.json()["data"]


@pytest.fixture
def customer():
    return Client()


@pytest.fixture
def admin():
    return Client(admin=True)


@pytest.fixture
def published(customer, admin):
    """פנייה עם הצעה מפורסמת; מחזיר (customer, inquiry, quote)."""
    inq = customer.submitted_inquiry()
    draft = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/recalculate", {"adjustments": []}))
    quote = data(admin.post(f"/api/admin/inquiries/{inq['id']}/quotes/publish", {"quote_id": draft["id"]}))
    return customer, inq, quote
