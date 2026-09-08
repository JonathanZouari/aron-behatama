"""אימות הנגר: JWT של Supabase Auth + בדיקה בטבלת admin_users.

תהליך:
1. הדפדפן מתחבר ל-Supabase (signInWithPassword) ומקבל access_token.
2. כל בקשת ניהול נשלחת עם Authorization: Bearer <token>.
3. השרת מאמת חתימה, תוקף ו-audience ("authenticated").
   - אם הוגדר SUPABASE_JWT_SECRET: אימות HS256 עם הסוד.
   - אחרת: אימות עם JWKS של הפרויקט (מפתחות אסימטריים, ES256/RS256).
4. ורק אם auth_user_id קיים ופעיל ב-admin_users — הבקשה מאושרת כנגר.

במצב דמו (DEMO_MODE=true ו-APP_ENV!=production) קיים נגר דמו ללא Supabase.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient

from app.config import Settings
from app.repositories.customer_repo import AdminRepository

DEMO_ADMIN = {"auth_user_id": "00000000-0000-0000-0000-000000000001", "email": "demo-carpenter@example.local",
              "display_name": "נגר דמו"}
DEMO_TOKEN = "demo-carpenter-token"


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Carpenter:
    id: str
    auth_user_id: str
    email: str
    display_name: str


class AdminAuthenticator:
    def __init__(self, settings: Settings, repo: AdminRepository):
        self.settings = settings
        self.repo = repo
        self._jwks: Optional[PyJWKClient] = None
        if settings.supabase_url and not settings.supabase_jwt_secret:
            self._jwks = PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)

    def authenticate(self, authorization_header: Optional[str]) -> Carpenter:
        token = _bearer(authorization_header)
        if self.settings.demo_mode and not self.settings.is_production and token == DEMO_TOKEN:
            admin = self.repo.upsert(DEMO_ADMIN["auth_user_id"], DEMO_ADMIN["email"], DEMO_ADMIN["display_name"])
            return Carpenter(admin["id"], admin["auth_user_id"], admin["email"], admin["display_name"])
        claims = self._verify(token)
        auth_user_id = claims.get("sub")
        if not auth_user_id:
            raise AuthError("טוקן ללא מזהה משתמש")
        admin = self.repo.get_by_auth_user(auth_user_id)
        if admin is None:
            raise AuthError("המשתמש אינו נגר מורשה", 403)
        return Carpenter(admin["id"], admin["auth_user_id"], admin["email"], admin["display_name"])

    def _verify(self, token: str) -> dict:
        if self.settings.demo_mode:
            raise AuthError("במצב דמו יש להתחבר עם כפתור הדמו")
        try:
            if self.settings.supabase_jwt_secret:
                return jwt.decode(token, self.settings.supabase_jwt_secret, algorithms=["HS256"],
                                  audience="authenticated", leeway=10)
            assert self._jwks is not None
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            return jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"],
                              audience="authenticated", leeway=10)
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("ההתחברות פגה, יש להתחבר מחדש") from exc
        except jwt.PyJWTError as exc:
            raise AuthError("טוקן לא תקין") from exc


def _bearer(header: Optional[str]) -> str:
    if not header or not header.lower().startswith("bearer "):
        raise AuthError("נדרשת התחברות")
    token = header[7:].strip()
    if not token or len(token) > 4096:
        raise AuthError("נדרשת התחברות")
    return token


def now_ts() -> int:
    return int(time.time())
