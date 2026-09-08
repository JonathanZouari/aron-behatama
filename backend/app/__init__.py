"""Flask application factory של ״ארון בהתאמה״."""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request

from .config import load_settings
from .container import Container, build_container
from .repositories.inquiry_repo import ConflictError
from .services.auth_admin import AuthError
from .services.inquiry_service import AIUnavailable, ValidationFailed
from .services.quote_service import QuoteError
from .services.security import SecurityError, apply_security_headers, ensure_csrf_cookie, verify_origin
from .services.status_machine import InvalidTransition


def create_app(container: Container | None = None, run_migrations: bool = False) -> Flask:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if container is None:
        settings = load_settings()
        container = build_container(settings)
        # במצב דמו מקומי הסכמה והנתונים נוצרים אוטומטית; בסביבות מחוברות מריצים migrations במפורש.
        if settings.demo_mode or run_migrations:
            container.db.run_migrations()
        if settings.demo_mode:
            from .seed.demo_data import seed_demo

            seed_demo(container)
    settings = container.settings

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.session_secret,
        SESSION_COOKIE_NAME="aron_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=settings.is_production or os.environ.get("FORCE_SECURE_COOKIES") == "true",
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=settings.max_body_bytes,
        JSON_AS_ASCII=False,
    )
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions["container"] = container

    from .routes import admin_customers, admin_inquiries, admin_pricebook, admin_quotes, health, public_chat, \
        public_inquiries, public_quotes

    for bp in (health.bp, public_inquiries.bp, public_chat.bp, public_quotes.bp, admin_inquiries.bp,
               admin_quotes.bp, admin_pricebook.bp, admin_customers.bp):
        app.register_blueprint(bp)

    @app.before_request
    def _before():
        g.container = container
        verify_origin(request, settings.frontend_origin)

    @app.after_request
    def _after(response):
        response = ensure_csrf_cookie(response)
        return apply_security_headers(response, settings.is_production)

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    def _err(message: str, status: int, **extra):
        return jsonify({"success": False, "error": message, **extra}), status

    @app.errorhandler(SecurityError)
    @app.errorhandler(AuthError)
    @app.errorhandler(QuoteError)
    def _domain(exc):
        return _err(str(exc), exc.status)

    @app.errorhandler(ValidationFailed)
    def _validation(exc):
        return _err(str(exc), 422, errors=exc.errors)

    @app.errorhandler(ConflictError)
    def _conflict(exc):
        return _err(str(exc), 409)

    @app.errorhandler(InvalidTransition)
    def _transition(exc):
        return _err(str(exc), 409)

    @app.errorhandler(AIUnavailable)
    def _ai(exc):
        return _err(str(exc), 503, ai_unavailable=True)

    @app.errorhandler(404)
    def _not_found(_exc):
        return _err("לא נמצא", 404)

    @app.errorhandler(413)
    def _too_large(_exc):
        return _err("הבקשה גדולה מדי", 413)

    @app.errorhandler(Exception)
    def _unexpected(exc):
        app.logger.exception("unhandled error: %s", type(exc).__name__)
        return _err("שגיאה פנימית", 500)
