"""בסיס משותף ל-repositories: מזהים, זמנים ואירועים."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from .db import Database, J, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


def as_bool(value: Any) -> bool:
    """SQLite מחזיר 0/1; Postgres מחזיר bool."""
    return bool(value)


class BaseRepository:
    def __init__(self, db: Database):
        self.db = db

    def add_event(self, inquiry_id: str, event_type: str, actor_type: str,
                  actor_id: Optional[str] = None, payload: Optional[dict] = None) -> None:
        self.db.execute(
            "insert into inquiry_events (id, inquiry_id, event_type, actor_type, actor_id, payload, created_at)"
            " values (?, ?, ?, ?, ?, ?, ?)",
            (new_id(), inquiry_id, event_type, actor_type, actor_id, J(payload or {}), utcnow()),
        )

    def list_events(self, inquiry_id: str) -> list[dict]:
        return self.db.fetch_all(
            "select * from inquiry_events where inquiry_id = ? order by created_at, id", (inquiry_id,)
        )
