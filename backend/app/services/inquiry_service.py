"""לוגיקת הפנייה מצד הלקוח: שיחה עם הסוכן, עדכון בטופס ושליחה לנגר.

השרת הוא מקור האמת: הוא מחשב שדות חסרים וסיבות לבדיקה ידנית בעצמו,
מאמת את פלט המודל, ומשתמש במספרי גרסה כדי שתשובת AI מאוחרת לא תדרוס
שינוי חדש שנעשה בטופס.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Protocol

from pydantic import ValidationError

from app.repositories.inquiry_repo import ConflictError, InquiryRepository
from app.schemas.agent_output import AgentOutput
from app.schemas.wardrobe_spec import SpecPatch, WardrobeSpec, apply_patch

from .status_machine import assert_inquiry_transition

log = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^0\d{1,2}-?\d{7}$|^\+?\d{9,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PlanningAgent(Protocol):
    def run(self, message: str, current_spec: WardrobeSpec, history: list[dict]) -> AgentOutput: ...


class AIUnavailable(Exception):
    """שירות ה-AI נכשל; הלקוח יכול להמשיך בטופס."""


class ValidationFailed(Exception):
    def __init__(self, message: str, errors: Optional[dict] = None):
        super().__init__(message)
        self.errors = errors or {}


def load_spec(spec_row: dict) -> WardrobeSpec:
    return WardrobeSpec.model_validate(spec_row["spec"])


def spec_payload(spec_row: dict, inquiry: dict) -> dict:
    """מפרט + מטא-נתונים לתצוגה ללקוח/נגר."""
    spec = load_spec(spec_row)
    return {
        "version": spec_row["version"],
        "customer_confirmed": spec_row["customer_confirmed"],
        "spec": spec.model_dump(),
        "missing_fields": spec.missing_fields(),
        "requires_manual_review": inquiry["requires_manual_review"],
        "manual_review_reasons": inquiry["manual_review_reasons"],
    }


class InquiryService:
    def __init__(self, repo: InquiryRepository, agent: PlanningAgent, agent_is_mock: bool):
        self.repo = repo
        self.agent = agent
        self.agent_is_mock = agent_is_mock

    # ---- שיחה --------------------------------------------------------------
    def chat_turn(self, inquiry: dict, message: str, base_version: int) -> dict:
        """מעבד הודעת לקוח. מחזיר reply, המפרט המעודכן והגרסה החדשה."""
        if inquiry["status"] != "collecting_details":
            raise ValidationFailed("הפנייה כבר נשלחה לנגר ולא ניתן להמשיך את השיחה")
        spec_row = self.repo.get_current_spec(inquiry["id"])
        if spec_row["version"] != base_version:
            raise ConflictError("המפרט עודכן בטופס בזמן השיחה — טען את הגרסה החדשה ושלח שוב")
        current = load_spec(spec_row)
        conversation = self.repo.get_conversation(inquiry["id"])
        history = [{"role": m["role"], "content": m["content"]} for m in self.repo.list_messages(conversation["id"])]
        self.repo.add_message(conversation["id"], "user", message)

        try:
            output = self.agent.run(message, current, history)
            output = AgentOutput.model_validate(output.model_dump())  # אימות חוזר בשרת
        except (ValidationError, Exception) as exc:  # noqa: BLE001 — כל כשל AI מטופל כאותו מקרה
            log.warning("AI agent failed: %s", type(exc).__name__)
            raise AIUnavailable("שירות העוזר אינו זמין כרגע") from exc

        # פלט המודל: None = "לא נמסר עכשיו" (אין למחוק ערכים קיימים דרך ה-AI)
        patch = SpecPatch(**output.proposed_spec_patch.model_dump(exclude_none=True))
        updated = apply_patch(current, patch)
        new_version = spec_row["version"]
        if patch.model_dump(exclude_unset=True):
            saved = self.repo.save_spec_version(inquiry, base_version, updated, source="ai")
            new_version = saved["version"]
        manual_reasons = self._manual_reasons(updated, output.manual_review_reasons)
        self._sync_manual_flags(inquiry["id"], manual_reasons)
        reply_meta = {
            "simulated": self.agent_is_mock,
            "missing_fields": updated.missing_fields(),
            "clarification_needed": output.clarification_needed,
        }
        self.repo.add_message(conversation["id"], "assistant", output.reply, reply_meta)
        return {
            "reply": output.reply,
            "simulated": self.agent_is_mock,
            "spec_version": new_version,
            "spec": updated.model_dump(),
            "missing_fields": updated.missing_fields(),
            "clarification_needed": output.clarification_needed,
            "requires_manual_review": bool(manual_reasons),
            "manual_review_reasons": manual_reasons,
        }

    def _manual_reasons(self, spec: WardrobeSpec, ai_reasons: list[str]) -> list[str]:
        reasons = list(spec.out_of_range_reasons())
        if spec.special_requirements and spec.special_requirements.strip():
            reasons.append("דרישות מיוחדות דורשות בדיקת נגר")
        for r in ai_reasons:
            cleaned = r.strip()[:200]
            if cleaned and cleaned not in reasons:
                reasons.append(cleaned)
        return reasons

    def _sync_manual_flags(self, inquiry_id: str, reasons: list[str]) -> None:
        from app.repositories.db import J

        self.repo.db.execute(
            "update inquiries set requires_manual_review = ?, manual_review_reasons = ? where id = ?",
            (bool(reasons), J(reasons), inquiry_id))

    # ---- טופס ----------------------------------------------------------------
    def update_spec_from_form(self, inquiry: dict, patch: SpecPatch, expected_version: int,
                              source: str = "customer_form", actor_id: Optional[str] = None) -> dict:
        if source == "customer_form" and inquiry["status"] != "collecting_details":
            raise ValidationFailed("לא ניתן לערוך מפרט אחרי השליחה לנגר")
        current = load_spec(self.repo.get_current_spec(inquiry["id"]))
        updated = apply_patch(current, patch)
        saved = self.repo.save_spec_version(inquiry, expected_version, updated, source=source, actor_id=actor_id)
        reasons = self._manual_reasons(updated, [])
        self._sync_manual_flags(inquiry["id"], reasons)
        refreshed = self.repo.get_inquiry(inquiry["id"])
        assert refreshed is not None
        return spec_payload(saved, refreshed)

    # ---- שליחה לנגר --------------------------------------------------------
    def submit(self, inquiry: dict, contact: dict, confirmed: bool, spec_version: int) -> dict:
        """אישור מפרט ושליחה. idempotent: פנייה שכבר נשלחה מוחזרת כפי שהיא."""
        if inquiry["status"] != "collecting_details":
            return inquiry
        if not confirmed:
            raise ValidationFailed("נדרש אישור מפורש של המפרט")
        errors = _validate_contact(contact)
        spec_row = self.repo.get_current_spec(inquiry["id"])
        if spec_row["version"] != spec_version:
            raise ConflictError("המפרט השתנה — עברו עליו שוב לפני האישור")
        spec = load_spec(spec_row)
        if (spec.delivery or spec.installation) and not (contact.get("city") or spec.city):
            errors["city"] = "נדרשת עיר להובלה או להתקנה"
        if errors:
            raise ValidationFailed("יש לתקן את הפרטים", errors)

        city = contact.get("city") or spec.city
        if city and spec.city != city:
            spec = spec.model_copy(update={"city": city})
        with self.repo.db.transaction():
            saved = self.repo.save_spec_version(inquiry, spec_version, spec, source="customer_form",
                                                customer_confirmed=True)
            fresh = self.repo.get_inquiry(inquiry["id"])
            assert fresh is not None
            reasons = self._manual_reasons(spec, list(fresh["manual_review_reasons"]))
            if spec.missing_fields():
                reasons.append("המפרט חסר: " + ", ".join(spec.missing_fields()))
            assert_inquiry_transition(fresh["status"], "awaiting_carpenter")
            from app.repositories.db import J, utcnow

            updated = self.repo.update_inquiry(
                fresh["id"], fresh["row_version"], status="awaiting_carpenter",
                contact_name=contact["full_name"].strip(), contact_phone=contact["phone"].strip(),
                contact_email=(contact.get("email") or "").strip() or None, contact_city=city,
                submitted_at=utcnow(), requires_manual_review=bool(reasons), manual_review_reasons=J(reasons))
            self.repo.add_event(inquiry["id"], "submitted", "customer", None,
                                {"spec_version": saved["version"], "manual_reasons": reasons})
            return updated


def _validate_contact(contact: dict) -> dict:
    errors = {}
    name = (contact.get("full_name") or "").strip()
    phone = (contact.get("phone") or "").strip().replace(" ", "")
    email = (contact.get("email") or "").strip()
    if len(name) < 2 or len(name) > 120:
        errors["full_name"] = "נא להזין שם מלא"
    if not PHONE_RE.match(phone):
        errors["phone"] = "נא להזין מספר טלפון תקין"
    if email and not EMAIL_RE.match(email):
        errors["email"] = "כתובת דוא״ל אינה תקינה"
    return errors
