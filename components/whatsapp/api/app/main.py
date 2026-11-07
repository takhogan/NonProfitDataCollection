"""FastAPI application: mounts routers and registers error handlers.

Routers are added per endpoint group described in the component README.
Implemented for the first deliverable: me, households, cases, webhooks.
Stubbed (empty) for later: water, charging, reviews.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    # Fail fast on missing/insecure production config before serving traffic.
    get_settings().validate_runtime()

    app = FastAPI(
        title="Aid Coordination API",
        version="0.1.0",
        description=(
            "Authenticated application API and inbound webhooks for the "
            "Venezuela power/water aid coordination platform."
        ),
    )

    register_error_handlers(app)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    # Routers are mounted here as they come online (see app/routers/).
    from app.routers import auth, cases, households, me, webhooks
    from app.routers import charging, reviews, water  # stubs

    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(households.router)
    app.include_router(cases.router)
    app.include_router(webhooks.router)
    app.include_router(water.router)
    app.include_router(charging.router)
    app.include_router(reviews.router)

    return app


app = create_app()
