"""Public dashboard contracts (CON-016; DOM-080, DOM-081, SEC-17).

These models are deliberately standalone: they inherit only from ``ContractModel``,
never from internal models, so a field added to an internal model cannot leak here.
A test asserts this. They never carry contact data, free text, points or exact counts.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .base import (
    AreaLevel,
    ContractModel,
    IndicatorSubject,
    LocalTimezone,
    NeedCategory,
    ShortText,
    UtcInstant,
    Uuid,
    not_asked,
)

CountBand = Literal["0", "1-9", "10-24", "25-49", "50-99", "100-249", "250+"]
BAND_EDGES: tuple[tuple[int, int | None, str], ...] = (
    (0, 0, "0"),
    (1, 9, "1-9"),
    (10, 24, "10-24"),
    (25, 49, "25-49"),
    (50, 99, "50-99"),
    (100, 249, "100-249"),
    (250, None, "250+"),
)


def band_for(count: int) -> str:
    """Map an exact count to its public band."""
    if count < 0:
        raise ValueError("count must be non-negative")
    for low, high, label in BAND_EDGES:
        if count >= low and (high is None or count <= high):
            return label
    raise AssertionError("unreachable")


class PublicArea(ContractModel):
    area_id: Uuid
    level: Literal["parish", "sector"]
    name: ShortText


class PublicStatusMix(ContractModel):
    available: CountBand
    unavailable: CountBand
    intermittent: CountBand
    unknown: CountBand


class PublicIndicatorCell(ContractModel):
    """A coarse, delayed public cell. Suppressed cells are omitted, not zeroed."""

    area: PublicArea
    subject: IndicatorSubject
    period_start: UtcInstant
    period_end: UtcInstant
    need_count_band: CountBand | None = Field(description="Null for service subjects.")
    status_mix: PublicStatusMix | None = Field(description="Null for need subjects.")
    coverage: Literal["none", "thin", "reported"]
    freshness: UtcInstant | None
    published_at: UtcInstant

    @model_validator(mode="after")
    def _check(self) -> "PublicIndicatorCell":
        is_need = self.subject in ("water_drinking", "water_other", "charging")
        if is_need != (self.need_count_band is not None) or is_need == (self.status_mix is not None):
            raise ValueError("need subjects carry need_count_band; service subjects carry status_mix")
        return self


class PublicMeetingPoint(ContractModel):
    kind: Literal["meeting_point"]
    name: ShortText
    description: Annotated[str, Field(min_length=1, max_length=500)] = not_asked()


class PublicSiteLocation(ContractModel):
    kind: Literal["public_site"]
    name: ShortText
    description: Annotated[str, Field(min_length=1, max_length=500)] = not_asked()


class PublicSchedule(ContractModel):
    """Human-readable schedule, already rendered in the org's timezone."""

    kind: Literal["one_off", "recurring"]
    summary_es: Annotated[str, Field(min_length=1, max_length=200)]
    timezone: LocalTimezone


class PublicActivity(ContractModel):
    """Only activities a provider marked public (DOM-081)."""

    activity_id: Uuid
    organization_name: ShortText
    type: Literal["water_distribution_point", "water_delivery", "charging_point", "other"]
    category: NeedCategory
    areas: Annotated[list[PublicArea], Field(min_length=1, max_length=100)]
    schedule: PublicSchedule
    public_location: Annotated[
        Union[PublicMeetingPoint, PublicSiteLocation], Field(discriminator="kind")
    ] | None
    status: Literal["planned", "active", "paused"]


# The public area level is never finer than the profile's public level; AreaLevel
# is imported for callers that need to compare levels.
__all__ = [
    "AreaLevel",
    "BAND_EDGES",
    "CountBand",
    "PublicActivity",
    "PublicArea",
    "PublicIndicatorCell",
    "PublicMeetingPoint",
    "PublicSchedule",
    "PublicSiteLocation",
    "PublicStatusMix",
    "band_for",
]
