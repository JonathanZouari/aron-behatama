"""שכבת גישה אחידה לבסיס הנתונים: SQLite (דמו) או PostgreSQL של Supabase.

עקרונות:
* השאילתות נכתבות פעם אחת עם `?` כ-placeholder; ל-Postgres ההמרה ל-%s נעשית כאן.
* ערכי JSON נעטפים ב-J(...) כדי שכל דיאלקט ישמור אותם נכון.
* datetime נשמר כ-UTC; ב-SQLite כמחרוזת ISO, ב-Postgres כ-timestamptz.
* כל שורה מוחזרת כ-dict, עם JSON מפוענח וזמנים כמחרוזות ISO אחידות.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from .sql_dialect import to_sqlite

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class J:
    """עטיפה לערך שיש לשמור כ-JSON."""

    def __init__(self, value: Any):
        self.value = value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class Database:
    def __init__(self, kind: str, conn: Any):
        if kind not in ("sqlite", "postgres"):
            raise ValueError(f"unsupported db kind: {kind}")
        self.kind = kind
        self._conn = conn
        self._depth = 0

    # ---- יצירה -----------------------------------------------------------
    @classmethod
    def sqlite(cls, path: str) -> "Database":
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        if path != ":memory:":
            conn.execute("pragma journal_mode = wal")
        return cls("sqlite", conn)

    @classmethod
    def postgres(cls, dsn: str) -> "Database":
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        return cls("postgres", conn)

    # ---- migrations -------------------------------------------------------
    def run_migrations(self) -> list[str]:
        """מריץ את קובצי ה-SQL לפי סדר, פעם אחת בלבד לכל קובץ."""
        self.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at text not null)"
        )
        applied = {r["name"] for r in self.fetch_all("select name from schema_migrations")}
        done = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            with self.transaction():
                self.execute_script(sql)
                self.execute("insert into schema_migrations (name, applied_at) values (?, ?)", (path.name, iso(utcnow())))
            done.append(path.name)
        return done

    def execute_script(self, sql: str) -> None:
        """מריץ קובץ SQL משפט אחרי משפט בתוך הטרנזקציה הנוכחית."""
        text = to_sqlite(sql) if self.kind == "sqlite" else sql
        for statement in _split_statements(text):
            self._conn.execute(statement)

    # ---- טרנזקציות ---------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[None]:
        """טרנזקציה מקוננת-בטוחה: רק החיצונית מבצעת commit/rollback."""
        if self._depth == 0:
            self._begin()
        self._depth += 1
        try:
            yield
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("commit")
        except Exception:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("rollback")
            raise

    def _begin(self) -> None:
        # שני הדיאלקטים במצב autocommit; הטרנזקציה נפתחת ונסגרת במפורש.
        self._conn.execute("begin immediate" if self.kind == "sqlite" else "begin")

    # ---- שאילתות -----------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cur = self._conn.execute(self._sql(sql), self._params(params))
        return cur.rowcount

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
        cur = self._conn.execute(self._sql(sql), self._params(params))
        row = cur.fetchone()
        return self._row(row) if row is not None else None

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self._conn.execute(self._sql(sql), self._params(params))
        return [self._row(r) for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()

    # ---- המרות -------------------------------------------------------------
    def _sql(self, sql: str) -> str:
        return sql if self.kind == "sqlite" else sql.replace("?", "%s")

    def _params(self, params: Sequence[Any]) -> tuple:
        return tuple(self._param(p) for p in params)

    def _param(self, value: Any) -> Any:
        if isinstance(value, J):
            if self.kind == "sqlite":
                return json.dumps(value.value, ensure_ascii=False, default=_json_default)
            from psycopg.types.json import Jsonb

            return Jsonb(value.value, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=_json_default))
        if isinstance(value, datetime):
            return iso(value) if self.kind == "sqlite" else value
        if isinstance(value, Decimal):
            return str(value) if self.kind == "sqlite" else value
        if isinstance(value, bool) and self.kind == "sqlite":
            return 1 if value else 0
        return value

    def _row(self, row: Any) -> dict:
        data = dict(row)
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = iso(value)
            elif isinstance(value, uuid.UUID):
                data[key] = str(value)
            elif isinstance(value, Decimal):
                data[key] = str(value)
            elif self.kind == "sqlite" and isinstance(value, str) and key in JSON_COLUMNS:
                data[key] = json.loads(value)
        return data


JSON_COLUMNS = {
    "manual_review_reasons", "meta", "spec", "missing_fields", "settings",
    "spec_snapshot", "pricing_snapshot", "adjustments", "payload",
}


def _split_statements(sql: str) -> list[str]:
    """מפצל לפי ';' אחרי הסרת הערות. מספיק לקובצי ה-DDL של הפרויקט."""
    no_comments = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    raise TypeError(f"cannot serialize {type(value)}")
