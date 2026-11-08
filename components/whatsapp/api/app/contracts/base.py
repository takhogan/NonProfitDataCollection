"""Base classes and shared primitive types for the v1 contracts (CON-002, CON-003, CON-005).

Conventions every contract module follows:

* ``ContractModel`` is strict, forbids extra fields, and rejects NaN/Infinity.
  It works in both Pydantic validation modes: ``model_validate_json`` (raw bytes)
  and ``model_validate`` on an already-parsed JSON dict, which is what FastAPI does.
* Identifiers and instants are strings on the wire. ``Uuid`` and ``UtcInstant``
  parse those strings explicitly, so strict mode does not reject them in
  Python mode, and they never accept integers or other loose inputs.
* Optional fields mean "not asked" (CON-003). They are declared with
  ``not_asked()``: they may be omitted, but explicit ``null`` is rejected.
  Serialize with ``to_wire()`` (``exclude_unset``) so omitted stays omitted.
* Tri-state fields carry an explicit ``"unknown"`` member. ``0`` and ``false``
  never stand in for unknown.
* Fields that are genuinely nullable (for example a profile-dependent count)
  are declared as ``X | None`` and are required, so ``null`` is always deliberate.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)


class ContractModel(BaseModel):
    """Strict boundary model: no extra fields, no silent coercion, finite numbers."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        allow_inf_nan=False,
        frozen=True,
        populate_by_name=False,
    )


def not_asked(**kwargs: Any) -> Any:
    """An optional field: omission means "not asked"; explicit null is rejected.

    The default is never validated or emitted in the JSON Schema, so the schema
    shows the field as optional with a non-null type.
    """
    return Field(default=None, json_schema_extra=_drop_default, **kwargs)


def _drop_default(schema: dict[str, Any]) -> None:
    schema.pop("default", None)


def to_wire(model: BaseModel) -> dict[str, Any]:
    """Serialize for the wire: JSON mode, omitted ("not asked") fields stay omitted."""
    return model.model_dump(mode="json", exclude_unset=True)


# ---------------------------------------------------------------------------
# UUID
# ---------------------------------------------------------------------------

UUID_PATTERN = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_UUID_RE = re.compile(UUID_PATTERN)


def _parse_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and _UUID_RE.match(value):
        return UUID(value)
    raise ValueError("must be a canonical hyphenated UUID string")


Uuid = Annotated[
    UUID,
    BeforeValidator(_parse_uuid),
    PlainSerializer(lambda u: str(u), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "uuid", "pattern": UUID_PATTERN}),
]

# ---------------------------------------------------------------------------
# UTC instant
# ---------------------------------------------------------------------------

# UTC only: "Z" or "+00:00". Other offsets are rejected rather than converted, so
# a wrong local offset cannot slip in silently (NFR-02).
UTC_INSTANT_PATTERN = (
    "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|\\+00:00)$"
)
_UTC_RE = re.compile(UTC_INSTANT_PATTERN)


def _parse_utc(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        if value.utcoffset().total_seconds() != 0:
            raise ValueError("instant must be in UTC")
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and _UTC_RE.match(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    raise ValueError("must be an ISO 8601 UTC instant ending in 'Z' or '+00:00'")


def _format_utc(value: datetime) -> str:
    text = value.astimezone(timezone.utc).isoformat()
    return text.replace("+00:00", "Z")


UtcInstant = Annotated[
    datetime,
    BeforeValidator(_parse_utc),
    PlainSerializer(_format_utc, return_type=str, when_used="json"),
    WithJsonSchema(
        {"type": "string", "format": "date-time", "pattern": UTC_INSTANT_PATTERN}
    ),
]


def _check_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("unknown IANA timezone") from exc
    return value


LocalTimezone = Annotated[
    str,
    StringConstraints(pattern="^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$", max_length=64),
    AfterValidator(_check_zone),
]
"""IANA timezone name, e.g. ``America/Caracas`` (display/collection metadata only)."""

# ---------------------------------------------------------------------------
# Small shared vocabularies
# ---------------------------------------------------------------------------

TimePrecision = Literal["exact", "approximate", "day", "unknown"]
YesNoUnknown = Literal["yes", "no", "unknown"]
AreaLevel = Literal["state", "municipality", "parish", "sector"]
PrivacyProfileName = Literal["protective", "standard"]
Locale = Literal["es", "en"]

NeedCategory = Literal["water_drinking", "water_other", "charging"]
ServiceType = Literal["electricity", "piped_water"]
IndicatorSubject = Literal["water_drinking", "water_other", "charging", "electricity", "piped_water"]
"""A need category or an observed service; indicator cells are keyed by either."""

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Slug = Annotated[str, StringConstraints(pattern="^[a-z0-9][a-z0-9_.-]{0,63}$")]
MessageKey = Annotated[str, StringConstraints(pattern="^[a-z0-9_]+(\\.[a-z0-9_]+)*$", max_length=128)]
NonNegativeInt = Annotated[int, Field(ge=0)]

OperationKey = Annotated[
    str, StringConstraints(pattern="^[A-Za-z0-9._:-]{8,128}$")
]
"""Client- or system-generated idempotency key (DOM-002). Unique per org and command."""

Cursor = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_-]{1,512}$")]
"""Opaque, URL-safe pagination cursor. Clients never construct or parse it."""

# E.164 phone number. Appears only in staff detail and contact-list models (CON-004).
PhoneE164 = Annotated[str, StringConstraints(pattern="^\\+[1-9][0-9]{6,14}$")]


class Quantity(ContractModel):
    """A non-negative amount with an explicit unit. Units are never mixed or converted."""

    value: Annotated[float, Field(ge=0, le=1_000_000)]
    unit: Literal["liters", "people", "devices"]


class AreaRef(ContractModel):
    """Reference to a data-driven area (state → municipality → parish → sector)."""

    area_id: Uuid
    level: AreaLevel


class Bucket(ContractModel):
    """A time bucket for indicators: [start, end) of the given width."""

    width: Literal["6h", "24h", "7d"]
    start: UtcInstant
    end: UtcInstant


T = TypeVar("T")


class Page(ContractModel, Generic[T]):
    """Cursor-paginated list response. ``next_cursor`` is null on the last page."""

    items: list[T]
    next_cursor: Cursor | None
