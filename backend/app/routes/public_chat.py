"""שיחת התכנון עם סוכן ה-AI (מוגבלת בקצב ובאורך)."""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import BaseModel, ConfigDict, Field

from app.services.security import client_key

from ._helpers import container, csrf_protected, customer_inquiry, ok, parse_body

bp = Blueprint("public_chat", __name__, url_prefix="/api")


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    base_version: int = Field(ge=1)


@bp.post("/inquiries/<inquiry_id>/chat")
@csrf_protected
def chat(inquiry_id: str):
    c = container()
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(ChatBody)
    if len(body.message) > c.settings.max_message_chars:
        raise ValueError("message too long")
    c.ai_limiter.check(client_key(request, fallback=inquiry["id"]))
    result = c.inquiry_service.chat_turn(inquiry, body.message.strip(), body.base_version)
    return ok(result)
