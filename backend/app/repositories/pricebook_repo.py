"""מחירון וקטלוג. כל שמירת מחירון יוצרת גרסה חדשה; הישנות נשמרות להיסטוריה."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.schemas.pricing import PriceBook, PriceBookItem, PriceBookSettings

from .base import BaseRepository, as_bool, new_id
from .db import J, utcnow


class PriceBookRepository(BaseRepository):
    # ---- מחירון ------------------------------------------------------------
    def get_active(self) -> Optional[PriceBook]:
        row = self.db.fetch_one("select * from price_books where is_active = ? order by version desc limit 1", (True,))
        return self._build(row) if row else None

    def get_by_version(self, version: int) -> Optional[PriceBook]:
        row = self.db.fetch_one("select * from price_books where version = ?", (version,))
        return self._build(row) if row else None

    def list_versions(self) -> list[dict]:
        rows = self.db.fetch_all("select id, version, is_demo, is_active, created_by, created_at from price_books order by version desc")
        return [{**r, "is_demo": as_bool(r["is_demo"]), "is_active": as_bool(r["is_active"])} for r in rows]

    def _build(self, row: dict) -> PriceBook:
        items = self.db.fetch_all(
            "select * from price_book_items where price_book_id = ? order by category, code", (row["id"],))
        return PriceBook(
            id=row["id"],
            version=row["version"],
            is_demo=as_bool(row["is_demo"]),
            settings=PriceBookSettings.model_validate(row["settings"]),
            items=[PriceBookItem(
                id=i["id"], code=i["code"], category=i["category"], name_he=i["name_he"], unit=i["unit"],
                unit_price=Decimal(i["unit_price"]), active=as_bool(i["active"]),
                includes_soft_close=as_bool(i["includes_soft_close"]), description_he=i["description_he"],
            ) for i in items],
        )

    def create_version(self, settings: PriceBookSettings, items: list[PriceBookItem],
                       is_demo: bool, created_by: Optional[str]) -> PriceBook:
        """שומר גרסה חדשה ומסמן אותה כפעילה. הגרסאות הקודמות נשארות."""
        with self.db.transaction():
            row = self.db.fetch_one("select coalesce(max(version), 0) as v from price_books")
            version = int(row["v"]) + 1
            book_id = new_id()
            self.db.execute("update price_books set is_active = ? where is_active = ?", (False, True))
            self.db.execute(
                "insert into price_books (id, version, is_demo, is_active, settings, created_by, created_at)"
                " values (?, ?, ?, ?, ?, ?, ?)",
                (book_id, version, is_demo, True, J(settings.model_dump(mode="json")), created_by, utcnow()))
            for item in items:
                self.db.execute(
                    "insert into price_book_items (id, price_book_id, code, category, name_he, unit, unit_price,"
                    " active, includes_soft_close, description_he) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_id(), book_id, item.code, item.category, item.name_he, item.unit, item.unit_price,
                     item.active, item.includes_soft_close, item.description_he))
            built = self.get_by_version(version)
            assert built is not None
            return built

    # ---- קטלוג -------------------------------------------------------------
    def list_catalog(self, active_only: bool = True) -> list[dict]:
        sql = "select * from catalog_items"
        params: list = []
        if active_only:
            sql += " where active = ?"
            params.append(True)
        sql += " order by kind, sort_order, name_he"
        return [{**r, "active": as_bool(r["active"])} for r in self.db.fetch_all(sql, params)]

    def upsert_catalog_item(self, kind: str, code: str, name_he: str, description_he: Optional[str],
                            sort_order: int = 0, active: bool = True) -> None:
        existing = self.db.fetch_one("select id from catalog_items where code = ?", (code,))
        if existing:
            self.db.execute(
                "update catalog_items set kind = ?, name_he = ?, description_he = ?, sort_order = ?, active = ?"
                " where code = ?", (kind, name_he, description_he, sort_order, active, code))
        else:
            self.db.execute(
                "insert into catalog_items (id, kind, code, name_he, description_he, active, sort_order)"
                " values (?, ?, ?, ?, ?, ?, ?)", (new_id(), kind, code, name_he, description_he, active, sort_order))
