"""Error envelope (CON-040).

Every error response body is ``{code, message_key, details, request_id}``. The
``message_key`` is a stable i18n key (the web app translates it); ``details`` lists
field-level issues with their JSON path, so nested validation errors stay locatable.
``from_validation_error`` turns a Pydantic ``ValidationError`` into an envelope.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError

from .base import ContractModel, MessageKey

ErrorCode = Literal[
    "validation_failed",
    "not_found",
    "forbidden",
    "conflict",
    "stale_version",
    "invalid_transition",
    "idempotency_conflict",
    "rate_limited",
    "unsupported_version",
    "profile_violation",
]

# HTTP status the API uses for each code.
HTTP_STATUS: dict[str, int] = {
    "validation_failed": 422,
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "stale_version": 409,
    "invalid_transition": 409,
    "idempotency_conflict": 409,
    "rate_limited": 429,
    "unsupported_version": 400,
    "profile_violation": 422,
}

RequestId = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9._:-]{8,128}$")]
PathSegment = Annotated[str, StringConstraints(min_length=1, max_length=128)] | Annotated[int, Field(ge=0)]


class ErrorDetail(ContractModel):
    """One field-level issue. ``loc`` is the JSON path, e.g. ``["needs", 0, "quantity", "unit"]``.

    Details never echo the submitted value, so they cannot leak personal data into logs.
    """

    loc: Annotated[list[PathSegment], Field(max_length=32)]
    issue: Annotated[str, StringConstraints(pattern="^[a-z0-9_]{1,64}$")]
    message_key: MessageKey


class ErrorEnvelope(ContractModel):
    code: ErrorCode
    message_key: MessageKey
    details: Annotated[list[ErrorDetail], Field(max_length=100)]
    request_id: RequestId


def _issue(error_type: str) -> str:
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in error_type.lower())
    return cleaned[:64] or "invalid"


def from_validation_error(exc: ValidationError, request_id: str) -> ErrorEnvelope:
    details = [
        ErrorDetail(
            loc=[seg for seg in err["loc"] if isinstance(seg, (str, int))][:32],
            issue=_issue(err["type"]),
            message_key=f"errors.validation.{_issue(err['type'])}",
        )
        for err in exc.errors(include_url=False, include_input=False)[:100]
    ]
    return ErrorEnvelope(
        code="validation_failed",
        message_key="errors.validation_failed",
        details=details,
        request_id=request_id,
    )


def profile_violation(loc: list[str | int], request_id: str) -> ErrorEnvelope:
    """A field the active privacy profile disallows (e.g. an address under ``protective``)."""
    return ErrorEnvelope(
        code="profile_violation",
        message_key="errors.profile_violation",
        details=[ErrorDetail(loc=loc, issue="disallowed_by_profile", message_key="errors.profile_violation.field")],
        request_id=request_id,
    )
