"""תשתית בדיקות: אפליקציה בדמו עם SQLite בזיכרון וסוכן מדומה."""
import pytest

from app import create_app
from app.config import load_settings
from app.container import build_container
from app.repositories.db import Database
from app.seed.demo_data import seed_reference_data

DEMO_ENV = {"APP_ENV": "development", "DEMO_MODE": "true", "SQLITE_PATH": ":memory:",
            "SESSION_SECRET": "test-secret-test-secret-test-secret-1234"}
ADMIN = {"Authorization": "Bearer demo-carpenter-token"}


@pytest.fixture
def container():
    settings = load_settings(DEMO_ENV)
    db = Database.sqlite(":memory:")
    db.run_migrations()
    c = build_container(settings, db)
    seed_reference_data(c)
    return c


@pytest.fixture
def app(container):
    return create_app(container)


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client) -> dict:
    """מבצע בקשה ראשונה כדי לקבל cookie CSRF ומחזיר את הכותרת המתאימה."""
    client.get("/health")
    token = client.get_cookie("csrf_token").value
    return {"X-CSRF-Token": token}


FULL_PATCH = {"width_cm": 240, "height_cm": 260, "depth_cm": 60, "body_material_id": "SANDWICH17",
              "front_material_id": "MDF_COATED", "finish_id": "FIN_OAK_LIGHT", "doors": 4, "internal_drawers": 2,
              "shelves": 6, "compartments": 2, "soft_close": True, "delivery": True, "installation": True,
              "city": "תל אביב"}


def create_submitted_inquiry(client, patch=None, contact=None):
    """זרימת לקוח מלאה דרך ה-API: יצירה → טופס → שליחה. מחזיר את הפנייה."""
    headers = csrf(client)
    inquiry = client.post("/api/inquiries", headers=headers).get_json()["data"]
    body = {"expected_version": inquiry["spec"]["version"], "patch": patch or FULL_PATCH}
    spec = client.patch(f"/api/inquiries/{inquiry['id']}/spec", json=body, headers=headers).get_json()["data"]
    submit = {"spec_version": spec["version"], "confirmed": True, "full_name": "דנה לוי", "phone": "0521234567",
              **(contact or {})}
    r = client.post(f"/api/inquiries/{inquiry['id']}/submit", json=submit, headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def publish_quote(client, inquiry_id, adjustments=None, manual_handled=False):
    headers = {**ADMIN, **csrf(client)}
    body = {"adjustments": adjustments or [], "manual_handled": manual_handled}
    draft = client.post(f"/api/admin/inquiries/{inquiry_id}/quotes/recalculate", json=body, headers=headers)
    assert draft.status_code == 200, draft.get_json()
    quote = draft.get_json()["data"]
    pub = client.post(f"/api/admin/inquiries/{inquiry_id}/quotes/publish", json={"quote_id": quote["id"]},
                      headers=headers)
    assert pub.status_code == 200, pub.get_json()
    return pub.get_json()["data"]
