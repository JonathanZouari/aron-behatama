"""API ניהולי לנגר: לוח בקרה, פניות, מפרט, הערות, היסטוריה. כל נתיב מוגן."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, request
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.wardrobe_spec import SpecPatch
from app.services.inquiry_service import spec_payload

from ._helpers import admin_inquiry, carpenter_required, container, csrf_protected, current_carpenter, ok, \
    parse_body
from ._serializers import admin_inquiry_row, admin_message, admin_quote

bp = Blueprint("admin_inquiries", __name__, url_prefix="/api/admin")


class SpecEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    patch: SpecPatch


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


@bp.get("/me")
@carpenter_required
def me():
    c = current_carpenter()
    s = container().settings
    return ok({"id": c.id, "email": c.email, "display_name": c.display_name,
               "app_env": s.app_env, "demo_mode": s.demo_mode})


@bp.get("/dashboard")
@carpenter_required
def dashboard():
    c = container()
    by_status = c.inquiries.count_by_status()
    quotes = c.quotes.count_by_status()
    return ok({
        "new_inquiries": by_status.get("awaiting_carpenter", 0) + by_status.get("change_requested", 0),
        "awaiting_review": by_status.get("awaiting_carpenter", 0),
        "change_requested": by_status.get("change_requested", 0),
        "published_quotes": quotes.get("published", 0),
        "accepted_quotes": quotes.get("accepted", 0),
        "by_status": by_status,
    })


@bp.get("/inquiries")
@carpenter_required
def list_inquiries():
    c = container()
    rows = c.inquiries.list_inquiries(
        search=request.args.get("q") or None,
        status=request.args.get("status") or None,
        manual_only=request.args.get("manual") == "1",
    )
    return ok([admin_inquiry_row(r, c.quotes.latest_quote(r["id"])) for r in rows])


def _detail(inquiry: dict) -> dict:
    c = container()
    spec_row = c.inquiries.get_current_spec(inquiry["id"])
    conversation = c.inquiries.get_conversation(inquiry["id"])
    quotes = c.quotes.list_quotes(inquiry["id"])
    return {
        **admin_inquiry_row({**inquiry, "spec": spec_row["spec"]}, c.quotes.latest_quote(inquiry["id"])),
        "contact": {"name": inquiry["contact_name"], "phone": inquiry["contact_phone"],
                    "email": inquiry["contact_email"], "city": inquiry["contact_city"]},
        "row_version": inquiry["row_version"],
        "manual_review_reasons": inquiry["manual_review_reasons"],
        "spec": spec_payload(spec_row, inquiry),
        "spec_versions": [{"version": v["version"], "source": v["source"], "customer_confirmed": v["customer_confirmed"],
                           "created_at": v["created_at"]} for v in c.inquiries.list_spec_versions(inquiry["id"])],
        "messages": [admin_message(m) for m in c.inquiries.list_messages(conversation["id"])],
        "notes": c.inquiries.list_notes(inquiry["id"]),
        "events": c.inquiries.list_events(inquiry["id"]),
        "quotes": [admin_quote(q, c.quotes.list_items(q["id"])) for q in quotes],
        "catalog": c.pricebooks.list_catalog(active_only=False),
    }


@bp.get("/inquiries/<inquiry_id>")
@carpenter_required
def get_inquiry(inquiry_id: str):
    return ok(_detail(admin_inquiry(inquiry_id)))


@bp.patch("/inquiries/<inquiry_id>/spec")
@carpenter_required
@csrf_protected
def edit_spec(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(SpecEditBody)
    container().inquiry_service.update_spec_from_form(inquiry, body.patch, body.expected_version,
                                                      source="carpenter", actor_id=current_carpenter().id)
    return ok(_detail(admin_inquiry(inquiry_id)))


@bp.post("/inquiries/<inquiry_id>/notes")
@carpenter_required
@csrf_protected
def add_note(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(NoteBody)
    note = container().inquiries.add_note(inquiry["id"], current_carpenter().id, body.body.strip())
    return ok(note, 201)


@bp.post("/inquiries/<inquiry_id>/reopen")
@carpenter_required
@csrf_protected
def reopen(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    container().quote_service.reopen_for_carpenter(inquiry, current_carpenter().id)
    return ok(_detail(admin_inquiry(inquiry_id)))


class CloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(default="", max_length=500)


@bp.post("/inquiries/<inquiry_id>/close")
@carpenter_required
@csrf_protected
def close(inquiry_id: str):
    inquiry = admin_inquiry(inquiry_id)
    body = parse_body(CloseBody)
    container().quote_service.close_inquiry(inquiry, current_carpenter().id, body.reason or "")
    return ok(_detail(admin_inquiry(inquiry_id)))
