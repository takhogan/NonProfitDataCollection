"""Derived aggregation tables (DB-013, DB-075..077, DOM-040..046, DOM-080/081).

Indicator and coverage cells are recomputed by worker jobs from source tables,
never edited by hand: only the worker role may write them. Readers outside the
worker go through the suppressing views ``v_indicator_cell`` /
``v_coverage_cell`` (DB-076). ``public_*`` tables hold only DOM-080/081 fields.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TenantOwned, check_in, org_fk, org_scoped, utcnow
from app.models.provider import ACTIVITY_TYPES
from app.models.report import NEED_CATEGORIES, SERVICE_TYPES

SUBJECTS = NEED_CATEGORIES + SERVICE_TYPES
BUCKETS = ("6h", "24h", "7d")
LEVELS = ("sector", "parish", "municipality", "state")
COVERAGE_LABELS = ("none", "thin", "reported")
CONFIDENCE_LABELS = ("low", "medium", "high")
COVERAGE_STATES = ("covered", "uncovered", "unknown")


class IndicatorCell(TenantOwned, Base):
    __tablename__ = "indicator_cell"
    __table_args__ = org_scoped(
        "indicator_cell",
        org_fk("indicator_cell", "area_id", "area"),
        org_fk("indicator_cell", "profile_version_id", "privacy_profile_version"),
        check_in("indicator_cell", "level", LEVELS),
        check_in("indicator_cell", "subject", SUBJECTS),
        check_in("indicator_cell", "bucket", BUCKETS),
        check_in("indicator_cell", "coverage_label", COVERAGE_LABELS),
        check_in("indicator_cell", "confidence_label", CONFIDENCE_LABELS),
        CheckConstraint(
            "active_needs >= 0 AND distinct_reporters >= 0 AND people_known >= 0 "
            "AND people_unknown_count >= 0 AND (distinct_households IS NULL OR distinct_households >= 0)",
            name="ck_indicator_cell_counts"),
        CheckConstraint("pending_review_share IS NULL OR "
                        "(pending_review_share >= 0 AND pending_review_share <= 1)",
                        name="ck_indicator_cell_review_share"),
        UniqueConstraint("organization_id", "area_id", "subject", "bucket", "bucket_start",
                         "method_version", name="uq_indicator_cell"),
        Index("ix_indicator_cell_lookup", "organization_id", "area_id", "subject", "bucket",
              "bucket_start"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(8), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_needs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_reporters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_households: Mapped[int | None] = mapped_column(Integer, nullable=True)
    people_known: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    people_unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urgency_mix: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    supply_mix: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status_mix: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    pending_review_share: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    freshness_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    coverage_label: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    confidence_label: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    confidence_reasons: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    method_version: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    input_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class CoverageCell(TenantOwned, Base):
    __tablename__ = "coverage_cell"
    __table_args__ = org_scoped(
        "coverage_cell",
        org_fk("coverage_cell", "area_id", "area"),
        check_in("coverage_cell", "category", NEED_CATEGORIES),
        check_in("coverage_cell", "coverage", COVERAGE_STATES),
        UniqueConstraint("organization_id", "area_id", "category", "method_version",
                         name="uq_coverage_cell"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    activity_ids: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    method_version: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class IndicatorDirtyCell(TenantOwned, Base):
    """Dirty-cell queue for incremental recompute (DB-075)."""

    __tablename__ = "indicator_dirty_cell"
    __table_args__ = org_scoped(
        "indicator_dirty_cell",
        org_fk("indicator_dirty_cell", "area_id", "area"),
        check_in("indicator_dirty_cell", "subject", SUBJECTS),
        UniqueConstraint("organization_id", "area_id", "subject", name="uq_indicator_dirty_cell"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExternalIndicator(TenantOwned, Base):
    """External context layer (Monitor Ciudad, satellites). Never adds to report
    counts (DOM-045)."""

    __tablename__ = "external_indicator"
    __table_args__ = org_scoped(
        "external_indicator",
        org_fk("external_indicator", "area_id", "area"),
        check_in("external_indicator", "subject", SERVICE_TYPES + NEED_CATEGORIES),
        Index("ix_external_indicator_lookup", "organization_id", "area_id", "subject",
              "observed_at"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False)
    indicator: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 default=utcnow)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PublicIndicatorCell(TenantOwned, Base):
    """Delayed, coarse, banded public snapshot (DOM-080). No contact data."""

    __tablename__ = "public_indicator_cell"
    __table_args__ = org_scoped(
        "public_indicator_cell",
        org_fk("public_indicator_cell", "area_id", "area"),
        check_in("public_indicator_cell", "level", LEVELS),
        check_in("public_indicator_cell", "subject", SUBJECTS),
        check_in("public_indicator_cell", "bucket", BUCKETS),
        check_in("public_indicator_cell", "coverage_label", COVERAGE_LABELS),
        UniqueConstraint("organization_id", "area_id", "subject", "bucket", "bucket_start",
                         name="uq_public_indicator_cell"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Copied so the public role never needs to read `area` (DB-003).
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(8), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_mix: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Banded counts, e.g. "0", "1-9", "10-24", "25+"; null for service subjects.
    need_count_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    coverage_label: Mapped[str] = mapped_column(String(16), nullable=False)
    freshness_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                   default=utcnow)


class PublicActivity(TenantOwned, Base):
    """Activities marked public (DOM-081)."""

    __tablename__ = "public_activity"
    __table_args__ = org_scoped(
        "public_activity",
        org_fk("public_activity", "area_id", "area"),
        check_in("public_activity", "type", ACTIVITY_TYPES),
        check_in("public_activity", "category", NEED_CATEGORIES),
    )

    # No FK to activity: snapshots survive activity edits and are rebuilt wholesale.
    activity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    public_location_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                   default=utcnow)
