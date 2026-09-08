"""עזרים משותפים ל-routes: גישה ל-container, קריאת JSON, הרשאות ותשובות אחידות."""
from __future__ import annotations

from functools import wraps
from typing import Any, Type, TypeVar

from flask import g, jsonify, request
from pydantic import BaseModel, ValidationError

from app.container import Container
from app.services.auth_admin import Carpenter
from app.services.customer_session import has_access
from app.services.inquiry_service import ValidationFailed
from app.services.quote_service import QuoteError
from app.services.security import verify_csrf

T = TypeVar("T", bound=BaseModel)


def container() -> Container:
    return g.container


def ok(data: Any = None, status: int = 200, **meta):
    body = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def parse_body(model: Type[T]) -> T:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationFailed("גוף הבקשה חייב להיות JSON")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        errors = {".".join(str(p) for p in e["loc"]): e["msg"] for e in exc.errors()}
        raise ValidationFailed("נתונים לא תקינים", errors) from exc


def customer_inquiry(inquiry_id: str) -> dict:
    """מחזיר את הפנייה רק אם ל-session של הלקוח יש גישה אליה."""
    if not has_access(inquiry_id):
        raise QuoteError("אין גישה לפנייה זו", 404)
    inquiry = container().inquiries.get_inquiry(inquiry_id)
    if inquiry is None:
        raise QuoteError("הפנייה לא נמצאה", 404)
    return inquiry


def csrf_protected(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        verify_csrf(request)
        return view(*args, **kwargs)

    return wrapper


def carpenter_required(view):
    """מאמת JWT + הרשאת נגר בכל endpoint ניהולי. RLS אינו תחליף לבדיקה זו."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        carpenter: Carpenter = container().auth.authenticate(request.headers.get("Authorization"))
        g.carpenter = carpenter
        return view(*args, **kwargs)

    return wrapper


def current_carpenter() -> Carpenter:
    return g.carpenter


def admin_inquiry(inquiry_id: str) -> dict:
    inquiry = container().inquiries.get_inquiry(inquiry_id)
    if inquiry is None:
        raise QuoteError("הפנייה לא נמצאה", 404)
    return inquiry
