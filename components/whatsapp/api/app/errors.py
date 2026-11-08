"""Structured application errors and FastAPI exception handlers (CON-040).

Every error response has one shape:

    {"code": str, "message_key": str, "details": object | null, "request_id": str}

`code` is a stable machine code from CON-040 (plus `unauthenticated`,
`capacity_exceeded` and `internal_error`). `message_key` is a translation key the
web app renders; the server never sends user-facing prose. `details` never echoes
request input (validation errors keep only the field location and error type), so
personal data a client sent cannot come back in an error or reach a log.

The human `message` passed to an AppError is for developers reading code and
tests. It is not sent to clients and not logged.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for structured, client-facing errors."""

    code = "error"
    status_code = 400

    def __init__(
        self,
        message: str = "",
        details: Any | None = None,
        *,
        message_key: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.message_key = message_key or f"errors.{self.code}"
        self.headers = headers or {}


class ValidationError(AppError):
    code = "validation_failed"
    status_code = 422


class Unauthenticated(AppError):
    """No valid session or credential. Always generic (no reason leaked)."""

    code = "unauthenticated"
    status_code = 401


class PermissionDenied(AppError):
    code = "forbidden"
    status_code = 403


class NotFound(AppError):
    # Used for tenant-scoped misses: we return 404 rather than 403 so the API
    # does not reveal that a resource exists in another organization.
    code = "not_found"
    status_code = 404


class Conflict(AppError):
    code = "conflict"
    status_code = 409


class StaleVersion(AppError):
    code = "stale_version"
    status_code = 409


class InvalidTransition(AppError):
    code = "invalid_transition"
    status_code = 409


class IdempotencyConflict(AppError):
    code = "idempotency_conflict"
    status_code = 409


class CapacityExceeded(AppError):
    code = "capacity_exceeded"
    status_code = 409


class RateLimited(AppError):
    code = "rate_limited"
    status_code = 429


class UnsupportedVersion(AppError):
    code = "unsupported_version"
    status_code = 400


class ProfileViolation(AppError):
    code = "profile_violation"
    status_code = 422


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def error_body(
    request: Request, code: str, message_key: str | None = None, details: Any | None = None
) -> dict:
    return {
        "code": code,
        "message_key": message_key or f"errors.{code}",
        "details": details,
        "request_id": request_id_of(request),
    }


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message_key: str | None = None,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    rid = request_id_of(request)
    hdrs = {"X-Request-ID": rid, "Cache-Control": "no-store"} if rid else {"Cache-Control": "no-store"}
    hdrs.update(headers or {})
    return JSONResponse(
        status_code=status_code,
        content=error_body(request, code, message_key, details),
        headers=hdrs,
    )


def _safe_validation_details(errors: list[dict]) -> list[dict]:
    """Keep only where and what kind of error; drop `input`, `ctx`, `msg` echoes."""
    return [{"loc": list(e.get("loc", ())), "type": e.get("type", "")} for e in errors]


_HTTP_CODES = {
    400: "validation_failed",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    409: "conflict",
    422: "validation_failed",
    429: "rate_limited",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            request, exc.status_code, exc.code, exc.message_key, exc.details, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request, 422, "validation_failed", details=_safe_validation_details(exc.errors())
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error" if exc.status_code < 500 else "internal_error")
        return error_response(request, exc.status_code, code, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the type and request id only: exception messages (e.g. SQL errors
        # with bound parameters) can carry personal data.
        log.error(
            "unhandled_exception",
            extra={"exc_type": type(exc).__name__, "request_id": request_id_of(request)},
        )
        return error_response(request, 500, "internal_error")
