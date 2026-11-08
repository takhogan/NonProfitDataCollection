"""Structured errors + handlers. Shape: {"error": {code, message, details}}."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    code = "error"
    status_code = 400

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(AppError):
    code = "validation_error"; status_code = 422


class PermissionDenied(AppError):
    code = "permission_denied"; status_code = 403


class NotFound(AppError):
    code = "not_found"; status_code = 404


class Conflict(AppError):
    code = "conflict"; status_code = 409


def _body(code: str, message: str, details: Any | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content=_body("validation_error", "Request validation failed", exc.errors()))
