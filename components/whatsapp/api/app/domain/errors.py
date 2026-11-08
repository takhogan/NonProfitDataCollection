"""Domain errors. Codes match the CON-040 error envelope so the API layer can map
them one-to-one (``app/errors.py`` belongs to the api session)."""
from __future__ import annotations

from typing import Any, Optional


class DomainError(Exception):
    code = "validation_failed"

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProfileViolation(DomainError):
    """A field the active privacy profile disallows (CON-040 ``profile_violation``)."""

    code = "profile_violation"

    def __init__(self, fields: list[str], profile_version: int, message: str = ""):
        self.fields = sorted(set(fields))
        super().__init__(
            message or f"fields not allowed by privacy profile v{profile_version}: {self.fields}",
            {"fields": self.fields, "profile_version": profile_version},
        )


class PolicyBelowMinimum(DomainError):
    """A profile setting below the platform minimum (e.g. k < 3)."""

    code = "validation_failed"


class InvalidTransition(DomainError):
    code = "invalid_transition"

    def __init__(self, machine: str, from_state: str, to_state: str, why: str = ""):
        super().__init__(
            f"{machine}: {from_state} -> {to_state} not allowed" + (f" ({why})" if why else ""),
            {"machine": machine, "from": from_state, "to": to_state},
        )


class Forbidden(DomainError):
    code = "forbidden"


class ValidationFailed(DomainError):
    code = "validation_failed"
