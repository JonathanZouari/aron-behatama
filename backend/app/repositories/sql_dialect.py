"""המרת DDL של PostgreSQL ל-SQLite עבור מצב הדמו.

ההמרה מכוונת רק לקובצי ה-migrations של הפרויקט (לא מתרגם SQL כללי):
uuid → text, jsonb → text, timestamptz → text, numeric(p,s) → numeric,
boolean נשאר (SQLite מקבל 0/1), ומשפטי RLS מוסרים.
"""
from __future__ import annotations

import re


def to_sqlite(sql: str) -> str:
    out = re.sub(r"^\s*alter table .* enable row level security;\s*$", "", sql, flags=re.MULTILINE | re.IGNORECASE)
    out = re.sub(r"\buuid\b", "text", out, flags=re.IGNORECASE)
    out = re.sub(r"\bjsonb\b", "text", out, flags=re.IGNORECASE)
    out = re.sub(r"\btimestamptz\b", "text", out, flags=re.IGNORECASE)
    out = re.sub(r"\bnumeric\(\d+,\s*\d+\)", "numeric", out, flags=re.IGNORECASE)
    # SQLite אינו תומך ב-"create index ... on t (col desc)" עם desc בתוך סוגריים בגרסאות ישנות — תומך, משאירים.
    return out
