"""אבטחת בקשות: CSRF (double-submit cookie), בדיקת Origin, הגבלת קצב וכותרות אבטחה."""
from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional
from urllib.parse import urlsplit

from flask import Request, Response, current_app, request

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SecurityError(Exception):
    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.status = status


def ensure_csrf_cookie(response: Response) -> Response:
    """מוודא שלדפדפן יש cookie CSRF (לא HttpOnly, כדי שה-JS יעתיק אותו לכותרת)."""
    if CSRF_COOKIE not in request.cookies:
        secure = current_app.config.get("SESSION_COOKIE_SECURE", False)
        response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False, secure=secure,
                            samesite="Lax", max_age=60 * 60 * 24 * 30, path="/")
    return response


def verify_csrf(req: Request) -> None:
    if req.method in SAFE_METHODS:
        return
    cookie = req.cookies.get(CSRF_COOKIE)
    header = req.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise SecurityError("בקשה נדחתה (CSRF). רענן את העמוד ונסה שוב", 403)


def verify_origin(req: Request, allowed_origin: str) -> None:
    """בבקשות state-changing דורשים Origin/Referer תואם כאשר הוגדר FRONTEND_ORIGIN."""
    if req.method in SAFE_METHODS or not allowed_origin:
        return
    source = req.headers.get("Origin") or req.headers.get("Referer")
    if not source:
        return  # לקוחות שאינם דפדפן (בדיקות/סקריפטים) — CSRF ו-session מגנים בנפרד
    parts = urlsplit(source)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin != allowed_origin:
        raise SecurityError("מקור הבקשה אינו מורשה", 403)


class RateLimiter:
    """מגביל קצב בזיכרון לפי מפתח (למשל מזהה session). מספיק לשרת יחיד."""

    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise SecurityError("יותר מדי בקשות. נסו שוב בעוד כמה דקות", 429)
            hits.append(now)


def apply_security_headers(response: Response, is_production: bool) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    if is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def client_key(req: Request, fallback: Optional[str] = None) -> str:
    """מפתח להגבלת קצב: קודם session של לקוח, אחרת כתובת IP."""
    forwarded = req.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (req.remote_addr or "unknown")
    return fallback or ip
