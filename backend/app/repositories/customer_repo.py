"""לקוחות, משתמשי נגר וטוקני גישה של לקוחות."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .base import BaseRepository, as_bool, new_id
from .db import utcnow


class CustomerRepository(BaseRepository):
    def create_customer(self, full_name: str, phone: str, email: Optional[str], city: Optional[str]) -> dict:
        customer_id = new_id()
        now = utcnow()
        self.db.execute(
            "insert into customers (id, full_name, phone, email, city, created_at, updated_at)"
            " values (?, ?, ?, ?, ?, ?, ?)", (customer_id, full_name, phone, email, city, now, now))
        return self.get_customer(customer_id)

    def get_customer(self, customer_id: str) -> Optional[dict]:
        return self.db.fetch_one("select * from customers where id = ?", (customer_id,))

    def list_customers(self, search: Optional[str] = None, limit: int = 200) -> list[dict]:
        sql = ("select c.*, count(i.id) as inquiry_count, max(i.created_at) as last_inquiry_at"
               " from customers c left join inquiries i on i.customer_id = c.id")
        params: list = []
        if search:
            like = f"%{search.strip()}%"
            sql += " where c.full_name like ? or c.phone like ?"
            params += [like, like]
        sql += " group by c.id order by c.created_at desc limit ?"
        params.append(limit)
        return self.db.fetch_all(sql, params)

    def link_inquiry(self, inquiry_id: str, customer_id: str, actor_id: str) -> None:
        """קישור מפורש של פנייה ללקוח קיים (אין מיזוג אוטומטי)."""
        self.db.execute("update inquiries set customer_id = ?, updated_at = ? where id = ?",
                        (customer_id, utcnow(), inquiry_id))
        self.add_event(inquiry_id, "customer_linked", "carpenter", actor_id, {"customer_id": customer_id})


class AdminRepository(BaseRepository):
    def get_by_auth_user(self, auth_user_id: str) -> Optional[dict]:
        row = self.db.fetch_one("select * from admin_users where auth_user_id = ? and active = ?", (auth_user_id, True))
        return {**row, "active": as_bool(row["active"])} if row else None

    def upsert(self, auth_user_id: str, email: str, display_name: str) -> dict:
        existing = self.db.fetch_one("select * from admin_users where auth_user_id = ?", (auth_user_id,))
        if existing:
            self.db.execute("update admin_users set email = ?, display_name = ?, active = ? where auth_user_id = ?",
                            (email, display_name, True, auth_user_id))
        else:
            self.db.execute(
                "insert into admin_users (id, auth_user_id, email, display_name, active, created_at)"
                " values (?, ?, ?, ?, ?, ?)", (new_id(), auth_user_id, email, display_name, True, utcnow()))
        result = self.get_by_auth_user(auth_user_id)
        assert result is not None
        return result


class AccessTokenRepository(BaseRepository):
    def create(self, inquiry_id: str, token_hash: str, expires_at: datetime) -> dict:
        token_id = new_id()
        self.db.execute(
            "insert into customer_access_tokens (id, inquiry_id, token_hash, expires_at, created_at)"
            " values (?, ?, ?, ?, ?)", (token_id, inquiry_id, token_hash, expires_at, utcnow()))
        self.add_event(inquiry_id, "access_link_created", "customer")
        row = self.db.fetch_one("select * from customer_access_tokens where id = ?", (token_id,))
        assert row is not None
        return row

    def find_valid(self, token_hash: str, now: datetime) -> Optional[dict]:
        row = self.db.fetch_one(
            "select * from customer_access_tokens where token_hash = ? and revoked_at is null", (token_hash,))
        if row is None:
            return None
        from .db import parse_dt

        expires = parse_dt(row["expires_at"])
        if expires is None or expires <= now:
            return None
        self.db.execute("update customer_access_tokens set last_used_at = ? where id = ?", (now, row["id"]))
        return row

    def revoke_all(self, inquiry_id: str) -> int:
        return self.db.execute(
            "update customer_access_tokens set revoked_at = ? where inquiry_id = ? and revoked_at is null",
            (utcnow(), inquiry_id))
