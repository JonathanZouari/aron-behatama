"""צפייה בהצעה, אישור ובקשת שינוי מצד הלקוח."""
from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, ConfigDict, Field

from ._helpers import container, csrf_protected, customer_inquiry, ok, parse_body
from ._serializers import public_quote

bp = Blueprint("public_quotes", __name__, url_prefix="/api")


class AcceptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: str = Field(max_length=64)
    version: int = Field(ge=1)


class ChangeRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: str = Field(max_length=64)
    message: str = Field(min_length=3, max_length=2000)


def _quote_view(inquiry: dict, quote: dict) -> dict:
    c = container()
    items = c.quotes.list_items(quote["id"])
    changes = c.quote_service.spec_changes_since_submission(inquiry, quote)
    return public_quote(quote, items, changes)


@bp.get("/inquiries/<inquiry_id>/quote")
def get_quote(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    quote = container().quote_service.customer_visible_quote(inquiry)
    return ok(_quote_view(inquiry, quote) if quote else None)


@bp.post("/inquiries/<inquiry_id>/quote/accept")
@csrf_protected
def accept_quote(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(AcceptBody)
    quote = container().quote_service.accept(inquiry, body.quote_id, body.version)
    return ok(_quote_view(inquiry, quote))


@bp.post("/inquiries/<inquiry_id>/quote/change-request")
@csrf_protected
def request_change(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(ChangeRequestBody)
    quote = container().quote_service.request_change(inquiry, body.quote_id, body.message.strip())
    return ok(_quote_view(inquiry, quote))
