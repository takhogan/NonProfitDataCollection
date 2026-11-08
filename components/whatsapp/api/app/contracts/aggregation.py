"""Area indicator, ranking and coverage contracts (CON-012, CON-013; DOM-040–DOM-052).

These are aggregate read models. They contain no personal fields, points or
addresses (CON-004, SEC-03). Suppression (DOM-044) has already run when a cell
reaches this model: a suppressed cell carries no metrics.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import (
    AreaRef,
    Bucket,
    ContractModel,
    IndicatorSubject,
    NeedCategory,
    NonNegativeInt,
    Slug,
    UtcInstant,
    Uuid,
)

NEED_SUBJECTS = ("water_drinking", "water_other", "charging")
SERVICE_SUBJECTS = ("electricity", "piped_water")

CoverageLabel = Literal["none", "thin", "reported"]
"""DOM-041: ``none`` = no reports in the bucket (unknown, never zero), ``thin`` = < k."""
ConfidenceLevel = Literal["low", "medium", "high"]
ConfidenceReason = Literal[
    "single_source",
    "few_sources",
    "many_independent_sources",
    "pending_review",
    "disputed",
    "reviewed",
    "stale",
    "fresh",
    "agrees_with_external",
    "disagrees_with_external",
    "no_external_context",
    "outlier_flagged",
]
CountUnit = Literal["reporters", "households"]


class UrgencyMix(ContractModel):
    urgent: NonNegativeInt
    routine: NonNegativeInt
    low: NonNegativeInt
    unknown: NonNegativeInt


class SupplyMix(ContractModel):
    none: NonNegativeInt
    little: NonNegativeInt
    some: NonNegativeInt
    unknown: NonNegativeInt


class StatusMix(ContractModel):
    available: NonNegativeInt
    unavailable: NonNegativeInt
    intermittent: NonNegativeInt
    unknown: NonNegativeInt


class Confidence(ContractModel):
    """A transparent label with its stated reasons, never a numeric truth score (DOM-042)."""

    level: ConfidenceLevel
    reasons: Annotated[list[ConfidenceReason], Field(min_length=1, max_length=12)]


class CellMetrics(ContractModel):
    """Counts for an unsuppressed cell.

    Need-category cells fill the need fields and leave ``status_mix`` null; service
    cells do the reverse. ``distinct_households`` is null in the protective profile,
    where the unit counted is reporters (DOM-015).
    """

    count_unit: CountUnit
    distinct_reporters: NonNegativeInt
    distinct_households: NonNegativeInt | None
    active_needs: NonNegativeInt | None
    people_affected_known: NonNegativeInt | None = Field(
        description="Sum of known people-affected values."
    )
    people_affected_unknown_count: NonNegativeInt | None = Field(
        description="Number of needs whose people-affected value is unknown or not asked."
    )
    urgency_mix: UrgencyMix | None
    supply_mix: SupplyMix | None
    status_mix: StatusMix | None
    pending_review_share: Annotated[float, Field(ge=0, le=1)]


class IndicatorCell(ContractModel):
    """One area × subject × time bucket (DOM-040). Provider and staff view."""

    area: AreaRef
    subject: IndicatorSubject
    bucket: Bucket
    suppressed: bool
    suppression: Literal["below_k", "merged_into_parent"] | None
    metrics: CellMetrics | None
    freshness: UtcInstant | None = Field(
        description="Newest confirmed observation in the cell; null when there is none."
    )
    coverage: CoverageLabel
    confidence: Confidence
    method_version: Slug
    profile_version: Annotated[int, Field(ge=1)]
    input_watermark: UtcInstant | None = Field(
        description="Latest included report (DOM-046); null when no report was included."
    )
    computed_at: UtcInstant

    @model_validator(mode="after")
    def _check(self) -> "IndicatorCell":
        if self.suppressed != (self.metrics is None):
            raise ValueError("a suppressed cell has no metrics; an unsuppressed cell has metrics")
        if self.suppressed != (self.suppression is not None):
            raise ValueError("suppression reason is set exactly when the cell is suppressed")
        if self.coverage == "none" and self.freshness is not None:
            raise ValueError("a cell with coverage 'none' has no freshness")
        m = self.metrics
        if m is not None:
            need_fields = (
                m.active_needs,
                m.people_affected_known,
                m.people_affected_unknown_count,
                m.urgency_mix,
                m.supply_mix,
            )
            if self.subject in NEED_SUBJECTS:
                if any(v is None for v in need_fields) or m.status_mix is not None:
                    raise ValueError("need-category cells set need metrics and no status_mix")
            else:
                if any(v is not None for v in need_fields) or m.status_mix is None:
                    raise ValueError("service cells set status_mix and no need metrics")
            if m.count_unit == "reporters" and m.distinct_households is not None:
                raise ValueError("distinct_households is null when counting reporters")
            if m.count_unit == "households" and m.distinct_households is None:
                raise ValueError("distinct_households is required when counting households")
        return self


RankingCriterion = Literal[
    "urgent_active_needs",
    "active_needs_per_reporter",
    "oldest_unmet_need_age_hours",
    "freshness_age_hours",
]
DEFAULT_RANKING_ORDER: tuple[str, ...] = (
    "urgent_active_needs",
    "active_needs_per_reporter",
    "oldest_unmet_need_age_hours",
    "freshness_age_hours",
)


class CriterionValue(ContractModel):
    criterion: RankingCriterion
    direction: Literal["desc", "asc"]
    value: Annotated[float, Field(ge=0)] | None


class AreaOfNeed(ContractModel):
    """A ranked cell, with the declared criteria used, in order (DOM-043). No hidden weights."""

    rank: Annotated[int, Field(ge=1)]
    cell: IndicatorCell
    criteria: Annotated[list[CriterionValue], Field(min_length=1, max_length=4)]
    ranking_method_version: Slug

    @model_validator(mode="after")
    def _check(self) -> "AreaOfNeed":
        if self.cell.suppressed:
            raise ValueError("suppressed cells are not ranked")
        if self.cell.subject not in NEED_SUBJECTS:
            raise ValueError("areas of need rank need-category cells")
        names = [c.criterion for c in self.criteria]
        if len(set(names)) != len(names):
            raise ValueError("criteria must not repeat")
        return self


class CoverageCell(ContractModel):
    """Area × category coverage (DOM-052). Says nothing about whether needs were met."""

    area: AreaRef
    category: NeedCategory
    coverage: Literal["covered", "uncovered", "unknown"]
    active_need_threshold: NonNegativeInt
    activity_ids: Annotated[list[Uuid], Field(max_length=200)] = Field(
        description="Active activities serving the cell. Internal-only activities count "
        "but other providers cannot read their details."
    )
    method_version: Slug
    computed_at: UtcInstant

    @model_validator(mode="after")
    def _check(self) -> "CoverageCell":
        if self.coverage == "covered" and not self.activity_ids:
            raise ValueError("a covered cell references at least one activity")
        if self.coverage == "uncovered" and self.activity_ids:
            raise ValueError("an uncovered cell has no serving activity")
        return self
