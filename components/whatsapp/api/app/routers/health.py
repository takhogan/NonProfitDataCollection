"""Liveness and readiness (API-110).

GET /livez   the process is up (no dependencies checked)
GET /readyz  the database answers `SELECT 1`; 503 `not_ready` otherwise
GET /health  alias of /livez, kept for the deployed smoke test
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import error_response

log = logging.getLogger("app.health")

router = APIRouter(tags=["system"])


@router.get("/livez")
@router.get("/health")
def livez() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # any driver error means not ready
        log.warning("readiness_failed", extra={"exc_type": type(exc).__name__})
        return error_response(request, 503, "not_ready",
                              details={"checks": {"database": "unavailable"}})
    return JSONResponse({"status": "ok", "checks": {"database": "ok"}})
