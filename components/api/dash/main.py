"""Dashboard API — FastAPI app serving the web dashboard.

Reads the shared database written by whatsapp/api (reports, conversations,
inbound events) and manages org settings. STEP 1 returns fake data; STEP 2
swaps in real DB queries.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dash.config import get_settings
from dash.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Dashboard API",
        version="0.1.0",
        description="NGO dashboard API (reads the shared intake database, manages org settings).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    from dash.routers import auth_org, dashboard
    app.include_router(auth_org.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
