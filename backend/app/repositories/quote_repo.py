"""הצעות מחיר: גרסאות, snapshot, סעיפים ונעילה אופטימית."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.schemas.pricing import PricingResult

from .base import BaseRepository, as_bool, new_id
from .db import J, utcnow
from .inquiry_repo import ConflictError

BOOL_COLUMNS = ("manual_handled", "is_stale")


class QuoteRepository(BaseRepository):
    def _quote(self, row: dict) -> dict:
        return {**row, **{c: as_bool(row[c]) for c in BOOL_COLUMNS}}

    def get_quote(self, quote_id: str) -> Optional[dict]:
        row = self.db.fetch_one("select * from quotes where id = ?", (quote_id,))
        return self._quote(row) if row else None

    def list_quotes(self, inquiry_id: str) -> list[dict]:
        rows = self.db.fetch_all("select * from quotes where inquiry_id = ? order by version", (inquiry_id,))
        return [self._quote(r) for r in rows]

    def latest_quote(self, inquiry_id: str, statuses: tuple[str, ...] = ()) -> Optional[dict]:
        sql = "select * from quotes where inquiry_id = ?"
        params: list = [inquiry_id]
        if statuses:
            sql += " and status in (" + ",".join("?" for _ in statuses) + ")"
            params += list(statuses)
        sql += " order by version desc limit 1"
        row = self.db.fetch_one(sql, params)
        return self._quote(row) if row else None

    def list_items(self, quote_id: str) -> list[dict]:
        return self.db.fetch_all("select * from quote_items where quote_id = ? order by position", (quote_id,))

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.fetch_all("select status, count(*) as c from quotes group by status")
        return {r["status"]: r["c"] for r in rows}

    def create_draft(self, inquiry_id: str, spec_version: int, spec_snapshot: dict,
                     pricing: PricingResult, adjustments: list[dict], delivery_zone_code: Optional[str],
                     terms_he: Optional[str], actor_id: Optional[str]) -> dict:
        """יוצר גרסת הצעה חדשה בסטטוס draft עם snapshot של המפרט והתמחור."""
        with self.db.transaction():
            row = self.db.fetch_one(
                "select coalesce(max(version), 0) as v from quotes where inquiry_id = ?", (inquiry_id,))
            version = int(row["v"]) + 1
            quote_id = new_id()
            now = utcnow()
            self.db.execute(
                "insert into quotes (id, inquiry_id, version, status, spec_version, spec_snapshot,"
                " pricing_snapshot, adjustments, delivery_zone_code, subtotal, vat_rate, vat_amount, total,"
                " terms_he, created_at, updated_at) values (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (quote_id, inquiry_id, version, spec_version, J(spec_snapshot),
                 J(pricing.model_dump(mode="json")), J(adjustments), delivery_zone_code,
                 pricing.subtotal, pricing.vat_rate, pricing.vat_amount, pricing.total, terms_he, now, now))
            self._replace_items(quote_id, pricing)
            self.add_event(inquiry_id, "quote_draft_created", "carpenter", actor_id, {"quote_version": version})
            return self.get_quote(quote_id)

    def _replace_items(self, quote_id: str, pricing: PricingResult) -> None:
        self.db.execute("delete from quote_items where quote_id = ?", (quote_id,))
        for position, line in enumerate(pricing.lines, start=1):
            self.db.execute(
                "insert into quote_items (id, quote_id, position, code, description, quantity, unit,"
                " unit_price, total, kind, reason) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), quote_id, position, line.code, line.description, line.quantity, line.unit,
                 line.unit_price, line.total, line.kind, line.reason))

    def update_draft_pricing(self, quote: dict, pricing: PricingResult, adjustments: list[dict],
                             delivery_zone_code: Optional[str], spec_version: int, spec_snapshot: dict,
                             manual_handled: bool, terms_he: Optional[str]) -> dict:
        """חישוב מחדש של טיוטה קיימת (רק draft ניתן לעריכה)."""
        if quote["status"] != "draft":
            raise ConflictError("רק טיוטה ניתנת לעריכה")
        with self.db.transaction():
            changed = self.db.execute(
                "update quotes set pricing_snapshot = ?, adjustments = ?, delivery_zone_code = ?,"
                " spec_version = ?, spec_snapshot = ?, subtotal = ?, vat_rate = ?, vat_amount = ?, total = ?,"
                " manual_handled = ?, is_stale = ?, terms_he = ?, row_version = row_version + 1, updated_at = ?"
                " where id = ? and row_version = ? and status = 'draft'",
                (J(pricing.model_dump(mode="json")), J(adjustments), delivery_zone_code, spec_version,
                 J(spec_snapshot), pricing.subtotal, pricing.vat_rate, pricing.vat_amount, pricing.total,
                 manual_handled, False, terms_he, utcnow(), quote["id"], quote["row_version"]))
            if changed != 1:
                raise ConflictError("ההצעה עודכנה במקביל — רענן ונסה שוב")
            self._replace_items(quote["id"], pricing)
            return self.get_quote(quote["id"])

    def transition(self, quote: dict, new_status: str, **fields) -> dict:
        """מעבר סטטוס עם בדיקת row_version (מונע פעולה כפולה)."""
        assignments = "".join(f", {k} = ?" for k in fields)
        params = [new_status, *fields.values(), utcnow(), quote["id"], quote["row_version"], quote["status"]]
        changed = self.db.execute(
            f"update quotes set status = ?{assignments}, row_version = row_version + 1, updated_at = ?"
            " where id = ? and row_version = ? and status = ?", params)
        if changed != 1:
            raise ConflictError("ההצעה השתנתה בינתיים — רענן ונסה שוב")
        return self.get_quote(quote["id"])

    def supersede_published(self, inquiry_id: str, except_quote_id: str) -> None:
        self.db.execute(
            "update quotes set status = 'superseded', row_version = row_version + 1, updated_at = ?"
            " where inquiry_id = ? and id <> ? and status = 'published'", (utcnow(), inquiry_id, except_quote_id))

    def set_change_request(self, quote: dict, text: str) -> dict:
        changed = self.db.execute(
            "update quotes set change_request_text = ?, row_version = row_version + 1, updated_at = ?"
            " where id = ? and row_version = ? and status = 'published'",
            (text, utcnow(), quote["id"], quote["row_version"]))
        if changed != 1:
            raise ConflictError("ההצעה השתנתה בינתיים — רענן ונסה שוב")
        return self.get_quote(quote["id"])


def money_str(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else f"{value:.2f}"
