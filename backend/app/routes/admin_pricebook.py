"""ניהול מחירון: צפייה בגרסה הפעילה ושמירה כגרסה חדשה."""
from __future__ import annotations

from flask import Blueprint
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pricing import PriceBook, PriceBookItem, PriceBookSettings

from ._helpers import carpenter_required, container, csrf_protected, current_carpenter, ok, parse_body

bp = Blueprint("admin_pricebook", __name__, url_prefix="/api/admin")


class PriceBookBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: PriceBookSettings
    items: list[PriceBookItem] = Field(min_length=1, max_length=300)
    is_demo: bool = False


def _view(book: PriceBook) -> dict:
    return book.model_dump(mode="json")


@bp.get("/pricebook")
@carpenter_required
def get_pricebook():
    c = container()
    book = c.pricebooks.get_active()
    return ok({"active": _view(book) if book else None, "versions": c.pricebooks.list_versions()})


@bp.put("/pricebook")
@carpenter_required
@csrf_protected
def save_pricebook():
    body = parse_body(PriceBookBody)
    codes = [i.code for i in body.items]
    if len(codes) != len(set(codes)):
        from app.services.inquiry_service import ValidationFailed

        raise ValidationFailed("קודי פריטים חייבים להיות ייחודיים")
    book = container().pricebooks.create_version(body.settings, body.items, body.is_demo, current_carpenter().id)
    return ok(_view(book), 201)
