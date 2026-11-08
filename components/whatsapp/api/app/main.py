"""FastAPI application: middleware, error handlers, and routers.

Routes:
- `/v1/...`        staff API, cookie sessions (API-001, API-010..013)
- `/orgs/{org_id}/...`, `/me`  legacy, deprecated (Deprecation header), kept
                   while the deployed service and old clients move to /v1
- `/auth/login`    development-only JWT login; not mounted in production
- `/webhooks/...`  WhatsApp (API-100/101)
- `/livez`, `/readyz`, `/health`  operations (API-110)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.logs import configure_logging
from app.auth.middleware import RequestContextMiddleware
from app.config import ConfigError, Settings, get_settings
from app.errors import register_error_handlers

log = logging.getLogger("app")


def validate_auth_runtime(s: Settings) -> None:
    """Production checks for the session/cookie settings added with /v1."""
    if not s.is_production:
        return
    problems = []
    if not s.session_cookie_secure:
        problems.append("SESSION_COOKIE_SECURE must be true")
    if s.web_origin and not s.web_origin.startswith("https://"):
        problems.append("WEB_ORIGIN must be https")
    if s.oidc_google_client_id and not s.oidc_google_redirect_uri.startswith("https://"):
        problems.append("OIDC_GOOGLE_REDIRECT_URI must be an https URL")
    if problems:
        raise ConfigError("Insecure auth configuration: " + "; ".join(problems))


def create_app() -> FastAPI:
    settings = get_settings()
    # Fail fast on missing/insecure production config before serving traffic.
    settings.validate_runtime()
    validate_auth_runtime(settings)
    configure_logging(settings.json_logs, settings.log_level)

    app = FastAPI(
        title="Data Aggregation API",
        version="0.2.0",
        description=(
            "Staff and provider API (/v1), WhatsApp webhooks, and operations "
            "endpoints for the outage and needs aggregation platform."
        ),
    )

    register_error_handlers(app)

    # Middleware: the last added is the outermost. Request context wraps CORS
    # so even preflight responses carry a request id.
    if settings.web_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.web_origin.rstrip("/")],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Idempotency-Key", "Retry-After"],
            max_age=600,
        )
    app.add_middleware(RequestContextMiddleware)

    from app.routers import admin, auth, cases, health, households, me, webhooks

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(admin.router)
    app.include_router(households.router)
    app.include_router(cases.router)
    app.include_router(webhooks.router)

    # Deprecated, unversioned routes.
    app.include_router(me.legacy_router)
    app.include_router(households.legacy_router)
    app.include_router(cases.legacy_router)
    if not settings.is_production:
        app.include_router(auth.dev_router)  # API-014: never in production

    if settings.is_production:
        # TODO: replace InMemoryAuthStore with the SQL store once the session
        # tables exist; until then sessions do not survive restarts and are not
        # shared between instances (run one instance).
        log.warning("auth_store_in_memory", extra={"event": "auth_store_in_memory"})

    return app


app = create_app()
