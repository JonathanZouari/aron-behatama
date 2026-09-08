"""לקוחות: רשימה, יצירה, היסטוריית פניות וקישור מפורש של פנייה ללקוח."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, request
from pydantic import BaseModel, ConfigDict, Field

from ._helpers import admin_inquiry, carpenter_required, container, csrf_protected, current_carpenter, ok, \
    parse_body
from ._serializers import admin_inquiry_row

bp = Blueprint("admin_customers", __name__, url_prefix="/api/admin")


class CustomerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    email: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=80)


class LinkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inquiry_id: str = Field(max_length=64)
    customer_id: Optional[str] = Field(default=None, max_length=64)
    create_from_contact: bool = False


@bp.get("/customers")
@carpenter_required
def list_customers():
    return ok(container().customers.list_customers(search=request.args.get("q") or None))


@bp.get("/customers/<customer_id>")
@carpenter_required
def get_customer(customer_id: str):
    c = container()
    customer = c.customers.get_customer(customer_id)
    if customer is None:
        from app.services.quote_service import QuoteError

        raise QuoteError("לקוח לא נמצא", 404)
    rows = c.inquiries.list_inquiries_for_customer(customer_id)
    return ok({**customer, "inquiries": [admin_inquiry_row(r, c.quotes.latest_quote(r["id"])) for r in rows]})


@bp.post("/customers")
@carpenter_required
@csrf_protected
def create_customer():
    body = parse_body(CustomerBody)
    return ok(container().customers.create_customer(body.full_name.strip(), body.phone.strip(), body.email, body.city), 201)


@bp.get("/customers/unlinked-inquiries")
@carpenter_required
def unlinked():
    c = container()
    return ok([admin_inquiry_row(r, None) for r in c.inquiries.list_unlinked_inquiries()])


@bp.post("/customers/link")
@carpenter_required
@csrf_protected
def link():
    """קישור מפורש. אין מיזוג אוטומטי לפי שם/טלפון."""
    c = container()
    body = parse_body(LinkBody)
    inquiry = admin_inquiry(body.inquiry_id)
    if body.create_from_contact:
        if not inquiry["contact_name"] or not inquiry["contact_phone"]:
            from app.services.inquiry_service import ValidationFailed

            raise ValidationFailed("לפנייה אין פרטי קשר ליצירת לקוח")
        customer = c.customers.create_customer(inquiry["contact_name"], inquiry["contact_phone"],
                                               inquiry["contact_email"], inquiry["contact_city"])
        customer_id = customer["id"]
    else:
        if not body.customer_id or c.customers.get_customer(body.customer_id) is None:
            from app.services.quote_service import QuoteError

            raise QuoteError("לקוח לא נמצא", 404)
        customer_id = body.customer_id
    c.customers.link_inquiry(inquiry["id"], customer_id, current_carpenter().id)
    return ok({"inquiry_id": inquiry["id"], "customer_id": customer_id})
