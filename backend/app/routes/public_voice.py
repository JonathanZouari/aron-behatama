"""שיחה קולית: יצירת session של GPT-Live עבור פנייה של הלקוח (SDP offer → SDP answer)."""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.ai.voice_session import VoiceUnavailable
from app.services.inquiry_service import ValidationFailed
from app.services.security import client_ip

from ._helpers import container, csrf_protected, customer_inquiry, ok, parse_body

bp = Blueprint("public_voice", __name__, url_prefix="/api")

MAX_SDP_CHARS = 16_000


class VoiceSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sdp: str = Field(min_length=1, max_length=MAX_SDP_CHARS)

    @field_validator("sdp")
    @classmethod
    def _looks_like_sdp(cls, value: str) -> str:
        if not value.startswith("v=0"):
            raise ValueError("SDP offer לא תקין")
        return value


@bp.post("/inquiries/<inquiry_id>/voice/session")
@csrf_protected
def create_voice_session(inquiry_id: str):
    c = container()
    inquiry = customer_inquiry(inquiry_id)
    body = parse_body(VoiceSessionBody)
    if inquiry["status"] != "collecting_details":
        raise ValidationFailed("הפנייה כבר נשלחה לנגר ולא ניתן להמשיך את השיחה")
    if c.voice is None:
        raise VoiceUnavailable("שיחה קולית אינה זמינה כרגע — אפשר להמשיך בכתב")
    # שלוש שכבות: לפנייה, לכתובת (פניות חדשות לא עוקפות) ותקציב יומי לכל השירות
    c.voice_limiter.check(f"voice:inquiry:{inquiry['id']}")
    c.voice_ip_limiter.check(f"voice:ip:{client_ip(request)}")
    c.voice_daily_limiter.check("voice:global")
    return ok(c.voice.create(body.sdp), 201)
