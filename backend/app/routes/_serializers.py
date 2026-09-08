"""המרת רשומות לתצוגה. הפרדה מפורשת בין מה שהלקוח רואה למה שהנגר רואה.

הלקוח לעולם אינו מקבל: הערות פנימיות, טיוטות, סיבות בדיקה ידנית פנימיות,
פירוט מחירי יחידה של המחירון או מזהי משתמשים.
"""
from __future__ import annotations

from typing import Optional

from app.services.status_machine import STATUS_LABELS_HE

PUBLIC_INQUIRY_FIELDS = ("id", "number", "status", "current_spec_version", "contact_name", "contact_city",
                         "submitted_at", "created_at")


def public_inquiry(inquiry: dict, spec_payload: dict) -> dict:
    return {
        **{k: inquiry.get(k) for k in PUBLIC_INQUIRY_FIELDS},
        "status_label": STATUS_LABELS_HE.get(inquiry["status"], inquiry["status"]),
        "requires_manual_review": inquiry["requires_manual_review"],
        "spec": spec_payload,
    }


def _line(item: dict) -> dict:
    return {
        "description": item["description"],
        "quantity": item["quantity"],
        "unit": item["unit"],
        "unit_price": item["unit_price"],
        "total": item["total"],
        "kind": item["kind"],
    }


def public_quote(quote: dict, items: list[dict], spec_changes: dict) -> dict:
    """הצעה מפורסמת/מאושרת/פגה בלבד. סעיפים ידניים מוצגים ללא ההסבר הפנימי."""
    return {
        "id": quote["id"],
        "version": quote["version"],
        "status": quote["status"],
        "status_label": STATUS_LABELS_HE.get(quote["status"], quote["status"]),
        "spec": quote["spec_snapshot"],
        "spec_changes": spec_changes,
        "items": [_line(i) for i in items],
        "subtotal": quote["subtotal"],
        "vat_rate": quote["vat_rate"],
        "vat_amount": quote["vat_amount"],
        "total": quote["total"],
        "currency": quote["currency"],
        "terms_he": quote["terms_he"],
        "published_at": quote["published_at"],
        "expires_at": quote["expires_at"],
        "accepted_at": quote["accepted_at"],
        "change_requested": bool(quote.get("change_request_text")),
        "can_accept": quote["status"] == "published" and not quote.get("change_request_text"),
    }


def admin_inquiry_row(inquiry: dict, latest_quote: Optional[dict]) -> dict:
    spec = inquiry.get("spec") or {}
    return {
        "id": inquiry["id"],
        "number": inquiry["number"],
        "created_at": inquiry["created_at"],
        "submitted_at": inquiry["submitted_at"],
        "contact_name": inquiry["contact_name"],
        "contact_phone": inquiry["contact_phone"],
        "status": inquiry["status"],
        "status_label": STATUS_LABELS_HE.get(inquiry["status"], inquiry["status"]),
        "dimensions": {"width_cm": spec.get("width_cm"), "height_cm": spec.get("height_cm"),
                       "depth_cm": spec.get("depth_cm")},
        "requires_manual_review": inquiry["requires_manual_review"],
        "customer_id": inquiry["customer_id"],
        "latest_quote": admin_quote_summary(latest_quote) if latest_quote else None,
    }


def admin_quote_summary(quote: dict) -> dict:
    return {
        "id": quote["id"], "version": quote["version"], "status": quote["status"],
        "status_label": STATUS_LABELS_HE.get(quote["status"], quote["status"]),
        "total": quote["total"], "is_stale": quote["is_stale"], "published_at": quote["published_at"],
        "expires_at": quote["expires_at"],
    }


def admin_quote(quote: dict, items: list[dict]) -> dict:
    return {
        **admin_quote_summary(quote),
        "spec_version": quote["spec_version"],
        "spec_snapshot": quote["spec_snapshot"],
        "pricing": quote["pricing_snapshot"],
        "adjustments": quote["adjustments"],
        "delivery_zone_code": quote["delivery_zone_code"],
        "items": [{**_line(i), "code": i["code"], "reason": i["reason"]} for i in items],
        "subtotal": quote["subtotal"], "vat_rate": quote["vat_rate"], "vat_amount": quote["vat_amount"],
        "terms_he": quote["terms_he"], "manual_handled": quote["manual_handled"],
        "change_request_text": quote["change_request_text"], "accepted_at": quote["accepted_at"],
        "cancelled_at": quote["cancelled_at"], "created_at": quote["created_at"], "updated_at": quote["updated_at"],
        "row_version": quote["row_version"],
    }


def admin_message(message: dict) -> dict:
    return {"id": message["id"], "role": message["role"], "content": message["content"],
            "meta": message["meta"], "created_at": message["created_at"]}


def public_message(message: dict) -> dict:
    return {"role": message["role"], "content": message["content"],
            "simulated": bool((message.get("meta") or {}).get("simulated")), "created_at": message["created_at"]}
