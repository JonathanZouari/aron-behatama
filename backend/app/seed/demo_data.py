"""נתוני הדגמה לסביבת פיתוח/דמו. לא נטענים בייצור.

יוצר: קטלוג, מחירון פיתוח, נגר דמו וכמה פניות בסטטוסים שונים. המחירים
מחושבים באמצעות מנוע התמחור ושירות ההצעות עצמם (לא ערכים קשיחים).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from app.schemas.pricing import ManualAdjustment
from app.schemas.wardrobe_spec import SpecPatch

from .catalog import CATALOG
from .pricebook_dev import DEV_ITEMS, DEV_SETTINGS

log = logging.getLogger(__name__)


def seed_reference_data(container) -> None:
    """קטלוג + מחירון — בטוח להרצה חוזרת. מתאים גם לסביבת dev מחוברת."""
    for item in CATALOG:
        container.pricebooks.upsert_catalog_item(**item)
    if container.pricebooks.get_active() is None:
        container.pricebooks.create_version(DEV_SETTINGS, DEV_ITEMS, is_demo=True, created_by="seed")
        log.info("נוצר מחירון פיתוח לדוגמה (גרסה 1)")


def seed_demo(container) -> None:
    """פניות לדוגמה. רץ פעם אחת (מזהה לפי מספר פנייה קיים)."""
    if container.settings.is_production:
        raise RuntimeError("אין לטעון נתוני הדגמה בייצור")
    seed_reference_data(container)
    if container.inquiries.list_inquiries(limit=1):
        return
    from app.services.auth_admin import DEMO_ADMIN

    admin = container.admins.upsert(DEMO_ADMIN["auth_user_id"], DEMO_ADMIN["email"], DEMO_ADMIN["display_name"])
    _seed_inquiries(container, admin["id"])
    log.info("נטענו פניות לדוגמה")


def _customer_flow(container, messages: list[str], form_patch: dict | None, contact: dict | None) -> dict:
    svc = container.inquiry_service
    inquiry = container.inquiries.create_inquiry("mock")
    version = 1
    for text in messages:
        result = svc.chat_turn(inquiry, text, version)
        version = result["spec_version"]
    if form_patch:
        payload = svc.update_spec_from_form(inquiry, SpecPatch(**form_patch), version)
        version = payload["version"]
    inquiry = container.inquiries.get_inquiry(inquiry["id"])
    if contact:
        inquiry = svc.submit(inquiry, contact, True, version)
    return inquiry


def _seed_inquiries(container, admin_id: str) -> None:
    qs = container.quote_service

    # 1. פנייה באמצע שיחה (איסוף פרטים)
    _customer_flow(container, ["אני רוצה ארון ברוחב 2 מטר וגובה 240 ס״מ עם 3 דלתות"], None, None)

    # 2. ממתינה לנגר, מפרט מלא
    full = {"width_cm": 240, "height_cm": 260, "depth_cm": 60, "body_material_id": "SANDWICH17",
            "front_material_id": "MDF_COATED", "finish_id": "FIN_OAK_LIGHT", "doors": 4, "internal_drawers": 2,
            "shelves": 6, "compartments": 2, "soft_close": True, "delivery": True, "installation": True,
            "city": "תל אביב"}
    _customer_flow(container, ["ארון 240 על 260, עומק 60, ארבע דלתות, שתי מגירות פנימיות ומדפים, גימור אלון בהיר"],
                   full, {"full_name": "דנה לוי", "phone": "0521234567", "email": "dana@example.com", "city": "תל אביב"})

    # 3. ממתינה לנגר עם בדיקה ידנית (דלתות הזזה + חסר עומק)
    _customer_flow(container, ["ארון 180 על 220 עם דלתות הזזה, 2 דלתות, בלי מגירות"],
                   {"body_material_id": "MDF18", "front_material_id": "MELAMINE_FRONT", "finish_id": "FIN_WHITE_MATTE",
                    "shelves": 4, "compartments": 2, "soft_close": False, "delivery": False, "installation": False},
                   {"full_name": "יוסי כהן", "phone": "0509876543"})

    # 4. הצעה פורסמה
    inq4 = _customer_flow(container, [], {**full, "width_cm": 200, "doors": 3, "internal_drawers": 0, "city": "חיפה"},
                          {"full_name": "מיכל אברהם", "phone": "0541112233", "city": "חיפה"})
    draft = qs.create_or_update_draft(inq4, [], None, False, None, admin_id)
    qs.publish(container.inquiries.get_inquiry(inq4["id"]), draft["id"], admin_id)

    # 5. הצעה אושרה, עם התאמה ידנית מנומקת
    inq5 = _customer_flow(container, [], {**full, "width_cm": 300, "doors": 5, "compartments": 3, "shelves": 9,
                                          "city": "רמת גן"},
                          {"full_name": "אורי שמעוני", "phone": "0533334444", "city": "רמת גן"})
    adj = [ManualAdjustment(description="הנחת לקוח חוזר", amount=Decimal("-300"), reason="לקוח שהזמין בעבר")]
    draft5 = qs.create_or_update_draft(inq5, adj, None, False, None, admin_id)
    pub5 = qs.publish(container.inquiries.get_inquiry(inq5["id"]), draft5["id"], admin_id)
    qs.accept(container.inquiries.get_inquiry(inq5["id"]), pub5["id"], pub5["version"])

    # 6. בקשת שינוי אחרי פרסום
    inq6 = _customer_flow(container, [], {**full, "finish_id": "FIN_WALNUT", "city": "הרצליה"},
                          {"full_name": "נועה פרידמן", "phone": "0587778888", "city": "הרצליה"})
    draft6 = qs.create_or_update_draft(inq6, [], None, False, None, admin_id)
    pub6 = qs.publish(container.inquiries.get_inquiry(inq6["id"]), draft6["id"], admin_id)
    qs.request_change(container.inquiries.get_inquiry(inq6["id"]), pub6["id"], "אפשר להוסיף עוד מגירה פנימית?")
    container.inquiries.add_note(inq6["id"], admin_id, "לבדוק אם יש מקום למגירה נוספת בתא השמאלי")
