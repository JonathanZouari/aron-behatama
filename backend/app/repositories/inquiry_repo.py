"""פניות, מפרטים (גרסאות), שיחות והודעות."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.schemas.wardrobe_spec import WardrobeSpec

from .base import BaseRepository, as_bool, new_id
from .db import J, utcnow


class ConflictError(Exception):
    """גרסה לא תואמת — מישהו אחר עדכן קודם."""


class InquiryRepository(BaseRepository):
    # ---- פניות -------------------------------------------------------------
    def create_inquiry(self, provider: str) -> dict:
        now = utcnow()
        inquiry_id = new_id()
        number = self._next_number(now)
        self.db.execute(
            "insert into inquiries (id, number, status, current_spec_version, created_at, updated_at)"
            " values (?, ?, 'collecting_details', 1, ?, ?)",
            (inquiry_id, number, now, now),
        )
        self.db.execute(
            "insert into wardrobe_specs (id, inquiry_id, version, spec, missing_fields, source, created_at)"
            " values (?, ?, 1, ?, ?, 'system', ?)",
            (new_id(), inquiry_id, J(WardrobeSpec().model_dump()), J(WardrobeSpec().missing_fields()), now),
        )
        self.db.execute(
            "insert into conversations (id, inquiry_id, provider, created_at) values (?, ?, ?, ?)",
            (new_id(), inquiry_id, provider, now),
        )
        self.add_event(inquiry_id, "inquiry_created", "customer")
        return self.get_inquiry(inquiry_id)

    def _next_number(self, now: datetime) -> str:
        year = now.year
        row = self.db.fetch_one("select count(*) as c from inquiries where number like ?", (f"AB-{year}-%",))
        return f"AB-{year}-{(row['c'] if row else 0) + 1:04d}"

    def get_inquiry(self, inquiry_id: str) -> Optional[dict]:
        row = self.db.fetch_one("select * from inquiries where id = ?", (inquiry_id,))
        return self._inquiry(row) if row else None

    def get_inquiry_by_number(self, number: str) -> Optional[dict]:
        row = self.db.fetch_one("select * from inquiries where number = ?", (number,))
        return self._inquiry(row) if row else None

    def _inquiry(self, row: dict) -> dict:
        return {**row, "requires_manual_review": as_bool(row["requires_manual_review"])}

    def list_inquiries(self, search: Optional[str] = None, status: Optional[str] = None,
                       manual_only: bool = False, limit: int = 100) -> list[dict]:
        sql = ("select i.*, s.spec from inquiries i"
               " join wardrobe_specs s on s.inquiry_id = i.id and s.version = i.current_spec_version where 1=1")
        params: list = []
        if status:
            sql += " and i.status = ?"
            params.append(status)
        if manual_only:
            sql += " and i.requires_manual_review = ?"
            params.append(True)
        if search:
            like = f"%{search.strip()}%"
            sql += " and (i.number like ? or i.contact_name like ? or i.contact_phone like ?)"
            params += [like, like, like]
        sql += " order by i.created_at desc limit ?"
        params.append(limit)
        return [self._inquiry(r) for r in self.db.fetch_all(sql, params)]

    def list_inquiries_for_customer(self, customer_id: str) -> list[dict]:
        rows = self.db.fetch_all(
            "select i.*, s.spec from inquiries i"
            " join wardrobe_specs s on s.inquiry_id = i.id and s.version = i.current_spec_version"
            " where i.customer_id = ? order by i.created_at desc", (customer_id,))
        return [self._inquiry(r) for r in rows]

    def list_unlinked_inquiries(self) -> list[dict]:
        rows = self.db.fetch_all(
            "select * from inquiries where customer_id is null and submitted_at is not null order by created_at desc")
        return [self._inquiry(r) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.fetch_all("select status, count(*) as c from inquiries group by status")
        return {r["status"]: r["c"] for r in rows}

    def update_inquiry(self, inquiry_id: str, expected_row_version: int, **fields) -> dict:
        """עדכון עם נעילה אופטימית: נכשל אם row_version השתנה."""
        assignments = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [utcnow(), inquiry_id, expected_row_version]
        changed = self.db.execute(
            f"update inquiries set {assignments}, row_version = row_version + 1, updated_at = ?"
            " where id = ? and row_version = ?", params)
        if changed != 1:
            raise ConflictError("הפנייה עודכנה במקביל — טען מחדש ונסה שוב")
        return self.get_inquiry(inquiry_id)

    # ---- מפרטים ------------------------------------------------------------
    def get_current_spec(self, inquiry_id: str) -> dict:
        row = self.db.fetch_one(
            "select s.* from wardrobe_specs s join inquiries i on i.id = s.inquiry_id"
            " and i.current_spec_version = s.version where s.inquiry_id = ?", (inquiry_id,))
        if row is None:
            raise LookupError("spec not found")
        return {**row, "customer_confirmed": as_bool(row["customer_confirmed"])}

    def list_spec_versions(self, inquiry_id: str) -> list[dict]:
        rows = self.db.fetch_all(
            "select * from wardrobe_specs where inquiry_id = ? order by version", (inquiry_id,))
        return [{**r, "customer_confirmed": as_bool(r["customer_confirmed"])} for r in rows]

    def save_spec_version(self, inquiry: dict, expected_version: int, spec: WardrobeSpec,
                          source: str, actor_id: Optional[str] = None,
                          customer_confirmed: bool = False) -> dict:
        """שומר גרסת מפרט חדשה. נכשל אם הגרסה הנוכחית אינה expected_version."""
        with self.db.transaction():
            current = self.get_inquiry(inquiry["id"])
            if current is None or current["current_spec_version"] != expected_version:
                raise ConflictError("המפרט עודכן בינתיים — רענן ונסה שוב")
            new_version = expected_version + 1
            self.db.execute(
                "insert into wardrobe_specs (id, inquiry_id, version, spec, missing_fields,"
                " customer_confirmed, source, actor_id, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), inquiry["id"], new_version, J(spec.model_dump()), J(spec.missing_fields()),
                 customer_confirmed, source, actor_id, utcnow()),
            )
            self.update_inquiry(inquiry["id"], current["row_version"], current_spec_version=new_version)
            # כל שינוי מפרט מסמן טיוטות קיימות כלא עדכניות
            self.db.execute(
                "update quotes set is_stale = ?, updated_at = ? where inquiry_id = ? and status = 'draft'",
                (True, utcnow(), inquiry["id"]))
            self.add_event(inquiry["id"], "spec_updated", "carpenter" if source == "carpenter" else
                           ("ai" if source == "ai" else "customer"), actor_id,
                           {"version": new_version, "customer_confirmed": customer_confirmed})
            return self.get_current_spec(inquiry["id"])

    # ---- שיחות והודעות -----------------------------------------------------
    def get_conversation(self, inquiry_id: str) -> dict:
        row = self.db.fetch_one("select * from conversations where inquiry_id = ?", (inquiry_id,))
        if row is None:
            raise LookupError("conversation not found")
        return row

    def add_message(self, conversation_id: str, role: str, content: str, meta: Optional[dict] = None) -> dict:
        message_id = new_id()
        self.db.execute(
            "insert into messages (id, conversation_id, role, content, meta, created_at) values (?, ?, ?, ?, ?, ?)",
            (message_id, conversation_id, role, content, J(meta or {}), utcnow()))
        return self.db.fetch_one("select * from messages where id = ?", (message_id,))

    def list_messages(self, conversation_id: str, limit: int = 200) -> list[dict]:
        return self.db.fetch_all(
            "select * from messages where conversation_id = ? order by created_at, id limit ?",
            (conversation_id, limit))

    # ---- הערות פנימיות ------------------------------------------------------
    def add_note(self, inquiry_id: str, author_id: str, body: str) -> dict:
        note_id = new_id()
        self.db.execute(
            "insert into internal_notes (id, inquiry_id, author_id, body, created_at) values (?, ?, ?, ?, ?)",
            (note_id, inquiry_id, author_id, body, utcnow()))
        return self.db.fetch_one("select * from internal_notes where id = ?", (note_id,))

    def list_notes(self, inquiry_id: str) -> list[dict]:
        return self.db.fetch_all(
            "select * from internal_notes where inquiry_id = ? order by created_at", (inquiry_id,))
