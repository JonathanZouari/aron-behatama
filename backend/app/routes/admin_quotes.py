"""API ניהולי להצעות: חישוב טיוטה, פרסום, ביטול."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pricing import ManualAdjustment

from ._helpers import admin_inquiry, carpenter_required, container, csrf_protected, current_carpenter, ok, \
    parse_body
from ._serializers import admin_quote

bp = Blueprint("admin_quotes", __name__, url_prefix="/api/admin")


class RecalculateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adjustments: list[ManualAdjustment] = Field(default_factory=list, max_length=20)
    delivery_zone_code: Optional[str] = Field(default=None, max_length=40)
    manual_handled: bool = False
    terms_he: Optional[str] = Field(default=None, max_length=2000)


class QuoteActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: str = Field(max_length=64)
    reason: Optional[str] = Field(default="", max_length=500)


def _view(quote: dict) -> dict:
    c = container()
    return admin_quote(quote, c.quotes.list_items(quote["id"]))


@bp.post("/inquiries/<inquiry_id>/quotes/recalculate")
@carpenter_required
@csrf_protected
def recalculate(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(RecalculateBody)
    quote = container().quote_service.create_or_update_draft(
        inquiry, body.adjustments, body.delivery_zone_code, body.manual_handled, body.terms_he,
        current_carpenter().id)
    return ok(_view(quote))


@bp.post("/inquiries/<inquiry_id>/quotes/publish")
@carpenter_required
@csrf_protected
def publish(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(QuoteActionBody)
    quote = container().quote_service.publish(inquiry, body.quote_id, current_carpenter().id)
    return ok(_view(quote))


@bp.post("/inquiries/<inquiry_id>/quotes/cancel")
@carpenter_required
@csrf_protected
def cancel(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(QuoteActionBody)
    quote = container().quote_service.cancel(inquiry, body.quote_id, current_carpenter().id, body.reason or "")
    return ok(_view(quote))
