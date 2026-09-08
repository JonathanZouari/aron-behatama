"""גישת לקוח: session חתום ב-cookie, קישור גישה אישי עם טוקן ו-hash.

* ה-session (Flask, cookie חתום, HttpOnly) שומר רשימת מזהי פניות שהדפדפן רשאי לראות.
* קישור אישי: טוקן אקראי חזק; בבסיס הנתונים נשמר רק SHA-256 שלו.
* בקבלת קישור, השרת מחליף את הטוקן ל-session ומפנה לכתובת נקייה ללא הטוקן.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from flask import session

from app.repositories.customer_repo import AccessTokenRepository
from app.repositories.db import utcnow

SESSION_KEY = "inquiry_ids"
TOKEN_TTL_DAYS = 30
MAX_SESSION_INQUIRIES = 10


def grant_access(inquiry_id: str) -> None:
    ids = [i for i in session.get(SESSION_KEY, []) if i != inquiry_id]
    ids.append(inquiry_id)
    session[SESSION_KEY] = ids[-MAX_SESSION_INQUIRIES:]
    session.permanent = True


def has_access(inquiry_id: str) -> bool:
    return inquiry_id in session.get(SESSION_KEY, [])


def current_inquiry_id() -> Optional[str]:
    ids = session.get(SESSION_KEY, [])
    return ids[-1] if ids else None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_link_token(repo: AccessTokenRepository, inquiry_id: str) -> tuple[str, str]:
    """מחזיר (token, expires_at_iso). הטוקן עצמו אינו נשמר."""
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(days=TOKEN_TTL_DAYS)
    row = repo.create(inquiry_id, hash_token(token), expires_at)
    return token, row["expires_at"]


def redeem_token(repo: AccessTokenRepository, token: str) -> Optional[str]:
    """ממיר טוקן תקף למזהה פנייה ומעניק גישה ב-session."""
    if not token or len(token) > 128:
        return None
    row = repo.find_valid(hash_token(token), utcnow())
    if row is None:
        return None
    grant_access(row["inquiry_id"])
    return row["inquiry_id"]
