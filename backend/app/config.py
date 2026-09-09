"""תצורת האפליקציה ממשתני סביבה, עם בדיקות בטיחות למצב דמו/ייצור."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_env: str
    demo_mode: bool
    sqlite_path: str
    session_secret: str
    frontend_origin: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str
    database_url: str
    openai_api_key: str
    openai_model: str
    ai_enabled: bool
    ai_messages_per_window: int = 20
    ai_window_seconds: int = 600
    max_message_chars: int = 2000
    max_body_bytes: int = 32 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def use_real_ai(self) -> bool:
        """סוכן OpenAI אמיתי בכל מצב (כולל דמו/SQLite) כאשר יש מפתח ו-AI_ENABLED."""
        return self.ai_enabled and bool(self.openai_api_key)


def load_settings(env: dict | None = None) -> Settings:
    e = env if env is not None else os.environ
    app_env = (e.get("APP_ENV") or "development").strip().lower()
    demo_mode = (e.get("DEMO_MODE") or "false").strip().lower() in ("1", "true", "yes", "on")

    if app_env == "production" and demo_mode:
        raise ConfigError("DEMO_MODE אסור כאשר APP_ENV=production — מצב דמו כולל מעקף התחברות")

    session_secret = e.get("SESSION_SECRET") or ""
    if app_env == "production" and len(session_secret) < 32:
        raise ConfigError("SESSION_SECRET חייב להיות לפחות 32 תווים בייצור")
    if not session_secret:
        session_secret = "dev-only-insecure-secret-change-me"

    settings = Settings(
        app_env=app_env,
        demo_mode=demo_mode,
        sqlite_path=e.get("SQLITE_PATH") or "data/demo.sqlite3",
        session_secret=session_secret,
        frontend_origin=(e.get("FRONTEND_ORIGIN") or "").rstrip("/"),
        supabase_url=(e.get("SUPABASE_URL") or "").rstrip("/"),
        supabase_service_role_key=e.get("SUPABASE_SERVICE_ROLE_KEY") or "",
        supabase_jwt_secret=e.get("SUPABASE_JWT_SECRET") or "",
        database_url=e.get("DATABASE_URL") or "",
        openai_api_key=e.get("OPENAI_API_KEY") or "",
        openai_model=e.get("OPENAI_MODEL") or "gpt-5-mini",
        ai_enabled=(e.get("AI_ENABLED") or "true").strip().lower() in ("1", "true", "yes", "on"),
    )
    if not settings.demo_mode:
        missing = [n for n, v in (("DATABASE_URL", settings.database_url),
                                  ("SUPABASE_URL", settings.supabase_url)) if not v]
        if missing:
            raise ConfigError(f"מחוץ למצב דמו נדרשים משתני הסביבה: {', '.join(missing)}")
    return settings
