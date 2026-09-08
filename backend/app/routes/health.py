"""בדיקת בריאות לשירות (Railway healthcheck)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from ._helpers import container

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    c = container()
    try:
        c.db.fetch_one("select 1 as ok")
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    status = 200 if db_ok else 503
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "app_env": c.settings.app_env,
        "demo_mode": c.settings.demo_mode,
        "ai": "simulated" if c.agent_is_mock else "openai",
        "database": c.db.kind,
    }), status


@bp.get("/api/health")
def api_health():
    return health()
