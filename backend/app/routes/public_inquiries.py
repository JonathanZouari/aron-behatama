"""API ציבורי של הלקוח: יצירת פנייה, מפרט, שליחה, מעקב וקישור גישה."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, redirect, request
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.wardrobe_spec import SpecPatch
from app.services import customer_session
from app.services.inquiry_service import spec_payload

from ._helpers import container, csrf_protected, customer_inquiry, ok, parse_body
from ._serializers import public_inquiry, public_message

bp = Blueprint("public_inquiries", __name__, url_prefix="/api")


class SpecUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    patch: SpecPatch


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_version: int = Field(ge=1)
    confirmed: bool
    full_name: str = Field(max_length=120)
    phone: str = Field(max_length=25)
    email: Optional[str] = Field(default=None, max_length=120)
    city: Optional[str] = Field(default=None, max_length=80)


def _inquiry_view(inquiry: dict) -> dict:
    c = container()
    spec_row = c.inquiries.get_current_spec(inquiry["id"])
    view = public_inquiry(inquiry, spec_payload(spec_row, inquiry))
    view["has_quote"] = c.quote_service.customer_visible_quote(inquiry) is not None
    return view


@bp.get("/catalog")
def catalog():
    return ok(container().pricebooks.list_catalog())


@bp.post("/inquiries")
@csrf_protected
def create_inquiry():
    c = container()
    inquiry = c.inquiries.create_inquiry("mock" if c.agent_is_mock else "openai")
    customer_session.grant_access(inquiry["id"])
    return ok(_inquiry_view(inquiry), 201)


@bp.get("/inquiries/current")
def current_inquiry():
    inquiry_id = customer_session.current_inquiry_id()
    if not inquiry_id:
        return ok(None)
    inquiry = container().inquiries.get_inquiry(inquiry_id)
    return ok(_inquiry_view(inquiry) if inquiry else None)


@bp.get("/inquiries/<inquiry_id>")
def get_inquiry(inquiry_id: str):
    return ok(_inquiry_view(customer_inquiry(inquiry_id)))


@bp.get("/inquiries/<inquiry_id>/messages")
def list_messages(inquiry_id: str):
    c = container()
    inquiry = customer_inquiry(inquiry_id)
    conversation = c.inquiries.get_conversation(inquiry["id"])
    return ok([public_message(m) for m in c.inquiries.list_messages(conversation["id"])])


@bp.patch("/inquiries/<inquiry_id>/spec")
@csrf_protected
def update_spec(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(SpecUpdateBody)
    return ok(container().inquiry_service.update_spec_from_form(inquiry, body.patch, body.expected_version))


@bp.post("/inquiries/<inquiry_id>/submit")
@csrf_protected
def submit(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(SubmitBody)
    contact = {"full_name": body.full_name, "phone": body.phone, "email": body.email, "city": body.city}
    updated = container().inquiry_service.submit(inquiry, contact, body.confirmed, body.spec_version)
    return ok(_inquiry_view(updated))


@bp.post("/inquiries/<inquiry_id>/access-link")
@csrf_protected
def create_access_link(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    token, expires_at = customer_session.create_access_link_token(container().tokens, inquiry["id"])
    # הקישור נבנה בצד הלקוח מאותו origin; הטוקן אינו נרשם ללוג
    return ok({"path": f"/api/access/{token}", "expires_at": expires_at})


@bp.get("/access/<token>")
def redeem_access(token: str):
    """מחליף טוקן קישור ב-session ומפנה לעמוד מעקב נקי (ללא הטוקן בכתובת)."""
    inquiry_id = customer_session.redeem_token(container().tokens, token)
    if inquiry_id is None:
        return redirect("/track.html?error=invalid_link", code=302)
    return redirect(f"/track.html?inquiry={inquiry_id}", code=302)


@bp.post("/inquiries/<inquiry_id>/access-link/revoke")
@csrf_protected
def revoke_access_links(inquiry_id: str):
    inquiry = customer_inquiry(inquiry_id)
    revoked = container().tokens.revoke_all(inquiry["id"])
    return ok({"revoked": revoked})
