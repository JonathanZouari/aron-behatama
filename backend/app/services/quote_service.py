"""הצעות מחיר: חישוב טיוטה, גרסאות, פרסום, אישור ובקשת שינוי.

* snapshot: הצעה שפורסמה שומרת מפרט ותמחור קפואים.
* גרסאות: כל שינוי יוצר גרסת הצעה חדשה; פרסום מסמן קודמות כ-superseded.
* תפוגה נבדקת בזמן הפעולה (אין משימה מתוזמנת).
* כל מעבר סטטוס משתמש ב-row_version כדי למנוע פעולה כפולה.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from app.repositories.db import parse_dt, utcnow
from app.repositories.inquiry_repo import ConflictError, InquiryRepository
from app.repositories.pricebook_repo import PriceBookRepository
from app.repositories.quote_repo import QuoteRepository
from app.schemas.pricing import ManualAdjustment, PriceBook, PricingResult
from app.schemas.wardrobe_spec import WardrobeSpec, spec_diff
from app.seed.catalog import zone_for_city

from .pricing_engine import price_spec
from .status_machine import InvalidTransition, assert_inquiry_transition, assert_quote_transition

DEFAULT_TERMS_HE = ("ההצעה כפופה למדידה סופית של הנגר לפני הייצור. "
                    "המחיר כולל מע\"מ כמפורט. תנאי תשלום ומועד אספקה ייקבעו עם הנגר בעת ההזמנה.")


class QuoteError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class QuoteService:
    def __init__(self, inquiries: InquiryRepository, quotes: QuoteRepository, pricebooks: PriceBookRepository,
                 is_production: bool):
        self.inquiries = inquiries
        self.quotes = quotes
        self.pricebooks = pricebooks
        self.is_production = is_production

    # ---- חישוב ---------------------------------------------------------------
    def _active_pricebook(self) -> PriceBook:
        book = self.pricebooks.get_active()
        if book is None:
            raise QuoteError("לא הוגדר מחירון פעיל", 409)
        return book

    def compute_draft(self, inquiry: dict, adjustments: list[ManualAdjustment],
                      delivery_zone_code: Optional[str]) -> tuple[PricingResult, dict, Optional[str]]:
        spec_row = self.inquiries.get_current_spec(inquiry["id"])
        spec = WardrobeSpec.model_validate(spec_row["spec"])
        zone = delivery_zone_code or zone_for_city(spec.city or inquiry.get("contact_city"))
        pricing = price_spec(spec, self._active_pricebook(), delivery_zone_code=zone, adjustments=adjustments)
        return pricing, spec_row, zone

    def create_or_update_draft(self, inquiry: dict, adjustments: list[ManualAdjustment],
                               delivery_zone_code: Optional[str], manual_handled: bool,
                               terms_he: Optional[str], actor_id: str) -> dict:
        """מחשב מחדש; מעדכן טיוטה קיימת או יוצר גרסת הצעה חדשה."""
        if inquiry["status"] in ("closed",):
            raise QuoteError("הפנייה סגורה", 409)
        pricing, spec_row, zone = self.compute_draft(inquiry, adjustments, delivery_zone_code)
        adjustments_json = [a.model_dump(mode="json") for a in adjustments]
        terms = terms_he if terms_he is not None else DEFAULT_TERMS_HE
        draft = self.quotes.latest_quote(inquiry["id"], statuses=("draft",))
        if draft:
            quote = self.quotes.update_draft_pricing(draft, pricing, adjustments_json, zone, spec_row["version"],
                                                     spec_row["spec"], manual_handled, terms)
        else:
            quote = self.quotes.create_draft(inquiry["id"], spec_row["version"], spec_row["spec"], pricing,
                                             adjustments_json, zone, terms, actor_id)
            if manual_handled:
                quote = self.quotes.update_draft_pricing(quote, pricing, adjustments_json, zone,
                                                         spec_row["version"], spec_row["spec"], True, terms)
        self.inquiries.add_event(inquiry["id"], "draft_recalculated", "carpenter", actor_id,
                                 {"quote_version": quote["version"], "complete": pricing.is_complete})
        return quote

    # ---- פרסום ---------------------------------------------------------------
    def publish(self, inquiry: dict, quote_id: str, actor_id: str) -> dict:
        quote = self._quote_of(inquiry, quote_id)
        if quote["status"] == "published":
            return quote  # פעולה כפולה — אין שינוי
        assert_quote_transition(quote["status"], "published")
        if quote["is_stale"]:
            raise QuoteError("המפרט שונה מאז החישוב — יש לחשב מחדש לפני פרסום", 409)
        if quote["total"] is None:
            raise QuoteError("להצעה אין מחיר סופי — יש להשלים סעיפים ידניים", 409)
        pricing = PricingResult.model_validate(quote["pricing_snapshot"])
        if pricing.manual_required and not quote["manual_handled"]:
            raise QuoteError("יש דרישות שלא תומחרו. סמן שטיפלת בהן לפני הפרסום", 409)
        book = self.pricebooks.get_by_version(pricing.pricebook_version) or self._active_pricebook()
        if self.is_production and (book.is_demo or not book.settings.confirmed_by_carpenter):
            raise QuoteError("בייצור נדרש מחירון שאומת על ידי הנגר (כולל שיעור מע\"מ) לפני פרסום", 409)
        with self.quotes.db.transaction():
            now = utcnow()
            expires = now + timedelta(days=book.settings.quote_validity_days)
            published = self.quotes.transition(quote, "published", published_at=now, expires_at=expires,
                                               change_request_text=None)
            self.quotes.supersede_published(inquiry["id"], published["id"])
            fresh = self.inquiries.get_inquiry(inquiry["id"])
            assert fresh is not None
            if fresh["status"] != "quote_available":
                assert_inquiry_transition(fresh["status"], "quote_available")
                self.inquiries.update_inquiry(fresh["id"], fresh["row_version"], status="quote_available")
            self.inquiries.add_event(inquiry["id"], "quote_published", "carpenter", actor_id,
                                     {"quote_id": published["id"], "quote_version": published["version"]})
            return published

    def cancel(self, inquiry: dict, quote_id: str, actor_id: str, reason: str) -> dict:
        quote = self._quote_of(inquiry, quote_id)
        if quote["status"] == "cancelled":
            return quote
        assert_quote_transition(quote["status"], "cancelled")
        with self.quotes.db.transaction():
            cancelled = self.quotes.transition(quote, "cancelled", cancelled_at=utcnow())
            fresh = self.inquiries.get_inquiry(inquiry["id"])
            assert fresh is not None
            if fresh["status"] in ("quote_available", "change_requested") and \
                    not self.quotes.latest_quote(inquiry["id"], statuses=("published",)):
                self.inquiries.update_inquiry(fresh["id"], fresh["row_version"], status="awaiting_carpenter")
            self.inquiries.add_event(inquiry["id"], "quote_cancelled", "carpenter", actor_id,
                                     {"quote_id": quote_id, "reason": reason})
            return cancelled

    def close_inquiry(self, inquiry: dict, actor_id: str, reason: str) -> dict:
        if inquiry["status"] == "closed":
            return inquiry
        assert_inquiry_transition(inquiry["status"], "closed")
        updated = self.inquiries.update_inquiry(inquiry["id"], inquiry["row_version"], status="closed",
                                                closed_at=utcnow())
        self.inquiries.add_event(inquiry["id"], "inquiry_closed", "carpenter", actor_id, {"reason": reason})
        return updated

    def reopen_for_carpenter(self, inquiry: dict, actor_id: str) -> dict:
        """אחרי בקשת שינוי: הנגר מסמן שהוא מטפל — הפנייה חוזרת לבדיקה."""
        assert_inquiry_transition(inquiry["status"], "awaiting_carpenter")
        updated = self.inquiries.update_inquiry(inquiry["id"], inquiry["row_version"], status="awaiting_carpenter")
        self.inquiries.add_event(inquiry["id"], "carpenter_reviewing", "carpenter", actor_id)
        return updated

    # ---- צד לקוח -------------------------------------------------------------
    def customer_visible_quote(self, inquiry: dict) -> Optional[dict]:
        """ההצעה שהלקוח רואה: המפורסמת/המאושרת האחרונה, לאחר בדיקת תפוגה. אין טיוטות."""
        quote = self.quotes.latest_quote(inquiry["id"], statuses=("published", "accepted", "expired"))
        if quote is None:
            return None
        quote = self._expire_if_needed(quote)
        return quote

    def _expire_if_needed(self, quote: dict) -> dict:
        expires = parse_dt(quote.get("expires_at"))
        if quote["status"] == "published" and expires and expires <= utcnow():
            try:
                return self.quotes.transition(quote, "expired")
            except ConflictError:
                return self.quotes.get_quote(quote["id"]) or quote
        return quote

    def accept(self, inquiry: dict, quote_id: str, version: int) -> dict:
        """אישור לקוח למזהה ולגרסה מדויקים. idempotent."""
        quote = self._quote_of(inquiry, quote_id)
        if quote["version"] != version:
            raise QuoteError("הגרסה שאושרה אינה הגרסה הנוכחית של ההצעה", 409)
        if quote["status"] == "accepted":
            return quote
        quote = self._expire_if_needed(quote)
        if quote["status"] != "published":
            raise QuoteError("לא ניתן לאשר הצעה שאינה מפורסמת (פג תוקף, בוטלה או הוחלפה)", 409)
        if quote.get("change_request_text"):
            raise QuoteError("קיימת בקשת שינוי פתוחה — יש לחכות לטיפול הנגר", 409)
        with self.quotes.db.transaction():
            accepted = self.quotes.transition(quote, "accepted", accepted_at=utcnow())
            fresh = self.inquiries.get_inquiry(inquiry["id"])
            assert fresh is not None
            assert_inquiry_transition(fresh["status"], "accepted")
            self.inquiries.update_inquiry(fresh["id"], fresh["row_version"], status="accepted")
            self.inquiries.add_event(inquiry["id"], "quote_accepted", "customer", None,
                                     {"quote_id": quote_id, "quote_version": version})
            return accepted

    def request_change(self, inquiry: dict, quote_id: str, text: str) -> dict:
        quote = self._quote_of(inquiry, quote_id)
        quote = self._expire_if_needed(quote)
        if quote["status"] != "published":
            raise QuoteError("ניתן לבקש שינוי רק להצעה מפורסמת", 409)
        with self.quotes.db.transaction():
            updated = self.quotes.set_change_request(quote, text)
            fresh = self.inquiries.get_inquiry(inquiry["id"])
            assert fresh is not None
            if fresh["status"] != "change_requested":
                assert_inquiry_transition(fresh["status"], "change_requested")
                self.inquiries.update_inquiry(fresh["id"], fresh["row_version"], status="change_requested")
            self.inquiries.add_event(inquiry["id"], "change_requested", "customer", None,
                                     {"quote_id": quote_id, "text": text[:2000]})
            return updated

    # ---- עזר -----------------------------------------------------------------
    def _quote_of(self, inquiry: dict, quote_id: str) -> dict:
        quote = self.quotes.get_quote(quote_id)
        if quote is None or quote["inquiry_id"] != inquiry["id"]:
            raise QuoteError("הצעה לא נמצאה", 404)
        return quote

    def spec_changes_since_submission(self, inquiry: dict, quote: dict) -> dict:
        """הבדלים בין המפרט שהלקוח אישר לבין המפרט שבהצעה (להדגשה ללקוח)."""
        versions = self.inquiries.list_spec_versions(inquiry["id"])
        confirmed = [v for v in versions if v["customer_confirmed"]]
        if not confirmed:
            return {}
        before = WardrobeSpec.model_validate(confirmed[-1]["spec"])
        after = WardrobeSpec.model_validate(quote["spec_snapshot"])
        return spec_diff(before, after)


__all__ = ["QuoteService", "QuoteError", "InvalidTransition", "DEFAULT_TERMS_HE"]
