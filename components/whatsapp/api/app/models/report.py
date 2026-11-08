"""Reports (assessments), observations, needs (DB-011, DOM-010..023).

In the pilot an *assessment* is called a **report**. Each report records the
``privacy_profile_version_id`` it was collected under. The profile-constraint
trigger (DB-023) rejects, per that version:

- ``report.encrypted_reporter_name`` when names are not allowed
- ``report.household_id`` when household records are not allowed
- ``report_location`` address/landmark unless location mode is ``address``
- ``report_location.restricted_point`` unless GPS is allowed

Precise location lives only in ``report_location`` (DB-052), a restricted
table that aggregation and provider views never read. All free text is
encrypted by the app before it reaches the database (DB-050).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Index, Integer, LargeBinary, Numeric, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base, GeoType, JSONType, TenantOwned, check_in, org_fk, org_scoped, utcnow,
)

SOURCE_CHANNELS = ("whatsapp", "phone", "volunteer_assisted")
REPORTING_RELATIONSHIPS = ("self", "household", "other_person", "area")
REPORT_STATUSES = ("draft", "confirmed", "superseded", "withdrawn", "abandoned")
REPORT_EXCLUSIONS = ("duplicate", "spam")  # only via a human review disposition
LOCATION_KINDS = ("meeting_point", "none_nearby", "address", "area_only", "unresolved")

SERVICE_TYPES = ("electricity", "piped_water")
OBSERVATION_STATUSES = ("available", "unavailable", "intermittent", "unknown")
SUBJECT_SCOPES = ("household", "area")
TIME_PRECISIONS = ("exact", "hour", "part_of_day", "day", "unknown")
SOURCE_KINDS = ("firsthand", "secondhand", "forwarded", "volunteer_observed")

NEED_CATEGORIES = ("water_drinking", "water_other", "charging")
WATER_CATEGORIES = ("water_drinking", "water_other")
NEED_UNITS = ("liters", "devices")
NEED_STATUSES = ("active", "stale", "resolved_by_reporter", "withdrawn", "expired")
REMAINING_SUPPLY = ("none", "little", "some", "unknown")
STATED_URGENCY = ("today", "this_week", "can_wait", "unknown")
DEVICE_TYPES = ("phone", "medical_device", "lamp", "power_bank", "laptop", "other")


class Report(TenantOwned, Base):
    __tablename__ = "report"
    __table_args__ = org_scoped(
        "report",
        org_fk("report", "privacy_profile_version_id", "privacy_profile_version"),
        org_fk("report", "reporter_key_id", "reporter_key"),
        org_fk("report", "household_id", "household"),
        org_fk("report", "campaign_id", "campaign"),
        org_fk("report", "conversation_id", "conversation"),
        org_fk("report", "questionnaire_version_id", "questionnaire_version"),
        org_fk("report", "area_id", "area"),
        org_fk("report", "meeting_point_id", "meeting_point"),
        org_fk("report", "supersedes_report_id", "report"),
        org_fk("report", "entered_by_membership_id", "organization_membership"),
        check_in("report", "source_channel", SOURCE_CHANNELS),
        check_in("report", "reporting_relationship", REPORTING_RELATIONSHIPS),
        check_in("report", "status", REPORT_STATUSES),
        check_in("report", "location_kind", LOCATION_KINDS),
        check_in("report", "excluded_reason", REPORT_EXCLUSIONS, nullable=True),
        CheckConstraint("supersedes_report_id IS NULL OR supersedes_report_id <> id",
                        name="ck_report_no_self_supersede"),
        CheckConstraint("status <> 'confirmed' OR confirmed_at IS NOT NULL",
                        name="ck_report_confirmed_at"),
        CheckConstraint("location_kind <> 'meeting_point' OR meeting_point_id IS NOT NULL",
                        name="ck_report_meeting_point"),
        Index("ix_report_org_area_time", "organization_id", "area_id", "submitted_at"),
        Index("ix_report_org_reporter", "organization_id", "reporter_key_id", "submitted_at"),
        Index("ix_report_org_status", "organization_id", "status"),
        # A report is superseded by at most one correction (DOM-012).
        Index("uq_report_supersedes", "organization_id", "supersedes_report_id", unique=True),
    )

    privacy_profile_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reporter_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    household_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    questionnaire_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    reporting_relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    # Sector (or coarser) the report is about; null while unresolved.
    area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    location_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="area_only")
    meeting_point_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Standard profile only (trigger-enforced). App-encrypted.
    encrypted_reporter_name: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Original answers, preserved (no free text in clear: encrypt or reference).
    answers_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_report_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entered_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    urgent_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluded_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportLocation(TenantOwned, Base):
    """Restricted precise location for a report (standard profile only)."""

    __tablename__ = "report_location"
    __table_args__ = org_scoped(
        "report_location",
        org_fk("report_location", "report_id", "report", ondelete="CASCADE"),
        UniqueConstraint("report_id", name="uq_report_location_report"),
        CheckConstraint("accuracy_meters IS NULL OR accuracy_meters >= 0",
                        name="ck_report_location_accuracy"),
    )

    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    encrypted_address: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encrypted_landmark: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    restricted_point: Mapped[str | None] = mapped_column(GeoType("POINT", 4326), nullable=True)
    accuracy_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precision: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="reporter")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Observation(TenantOwned, Base):
    __tablename__ = "observation"
    __table_args__ = org_scoped(
        "observation",
        org_fk("observation", "report_id", "report", ondelete="CASCADE"),
        org_fk("observation", "area_id", "area"),
        org_fk("observation", "outage_episode_id", "outage_episode"),
        org_fk("observation", "supersedes_observation_id", "observation"),
        check_in("observation", "service_type", SERVICE_TYPES),
        check_in("observation", "status", OBSERVATION_STATUSES),
        check_in("observation", "subject_scope", SUBJECT_SCOPES),
        check_in("observation", "time_precision", TIME_PRECISIONS),
        check_in("observation", "onset_precision", TIME_PRECISIONS, nullable=True),
        check_in("observation", "source_kind", SOURCE_KINDS),
        CheckConstraint(
            "observation_start_at IS NULL OR observation_end_at IS NULL "
            "OR observation_start_at <= observation_end_at",
            name="ck_observation_range"),
        CheckConstraint("supersedes_observation_id IS NULL OR supersedes_observation_id <> id",
                        name="ck_observation_no_self_supersede"),
        Index("ix_observation_org_time_service", "organization_id", "observed_at", "service_type"),
        Index("ix_observation_org_area", "organization_id", "area_id", "service_type"),
        Index("ix_observation_report", "organization_id", "report_id"),
    )

    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Denormalized from the report for aggregation without the report table.
    area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outage_episode_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="household")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # When the reporter observed it (best point estimate) plus the uncertainty window.
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    reported_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Caracas")
    # Estimated outage onset is distinct from observation time (DOM-013).
    outage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onset_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="firsthand")
    source_group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    supersedes_observation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Need(TenantOwned, Base):
    """A reported need. No assignment/allocation/closure workflow (DOM-022)."""

    __tablename__ = "need"
    __table_args__ = org_scoped(
        "need",
        org_fk("need", "report_id", "report", ondelete="CASCADE"),
        org_fk("need", "area_id", "area"),
        org_fk("need", "reporter_key_id", "reporter_key"),
        org_fk("need", "supersedes_need_id", "need"),
        check_in("need", "category", NEED_CATEGORIES),
        check_in("need", "unit", NEED_UNITS, nullable=True),
        check_in("need", "status", NEED_STATUSES),
        check_in("need", "remaining_supply", REMAINING_SUPPLY),
        check_in("need", "stated_urgency", STATED_URGENCY),
        # DB-020 units: liters only for water, devices only for charging.
        CheckConstraint(
            "unit IS NULL OR (unit = 'liters' AND category IN ('water_drinking', 'water_other')) "
            "OR (unit = 'devices' AND category = 'charging')",
            name="ck_need_unit_matches_category"),
        CheckConstraint("quantity IS NULL OR (quantity >= 0 AND unit IS NOT NULL)",
                        name="ck_need_quantity"),
        CheckConstraint("people_affected IS NULL OR people_affected >= 0",
                        name="ck_need_people"),
        CheckConstraint("refresh_prompt_count >= 0", name="ck_need_refresh_count"),
        CheckConstraint("supersedes_need_id IS NULL OR supersedes_need_id <> id",
                        name="ck_need_no_self_supersede"),
        Index("ix_need_org_area_status", "organization_id", "area_id", "category", "status"),
        Index("ix_need_org_reporter", "organization_id", "reporter_key_id", "status"),
        Index("ix_need_report", "organization_id", "report_id"),
    )

    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Denormalized from the report so indicator/contact-list SQL needs no report join.
    area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reporter_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    people_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    remaining_supply: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    stated_urgency: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    urgency_inputs: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Structured access flags, e.g. {"cannot_leave_home": true, "no_containers": true}.
    access_flags: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    encrypted_access_notes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    preferred_times: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    refresh_prompt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_refresh_prompt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_need_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class WaterNeedDetail(TenantOwned, Base):
    __tablename__ = "water_need_detail"
    __table_args__ = org_scoped(
        "water_need_detail",
        org_fk("water_need_detail", "need_id", "need", ondelete="CASCADE"),
        UniqueConstraint("need_id", name="uq_water_need_detail_need"),
        CheckConstraint("people_to_serve IS NULL OR people_to_serve >= 0",
                        name="ck_water_detail_people"),
        CheckConstraint("remaining_supply_hours IS NULL OR remaining_supply_hours >= 0",
                        name="ck_water_detail_hours"),
        CheckConstraint("container_capacity_liters IS NULL OR container_capacity_liters >= 0",
                        name="ck_water_detail_capacity"),
        CheckConstraint(
            "preferred_window_start IS NULL OR preferred_window_end IS NULL "
            "OR preferred_window_start <= preferred_window_end",
            name="ck_water_detail_window"),
    )

    need_id: Mapped[str] = mapped_column(String(36), nullable=False)
    intended_use: Mapped[str | None] = mapped_column(String(32), nullable=True)
    people_to_serve: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_supply_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_containers: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    container_capacity_liters: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    receiving_assistance_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    preferred_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quantity_estimation_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ChargingNeedDetail(TenantOwned, Base):
    __tablename__ = "charging_need_detail"
    __table_args__ = org_scoped(
        "charging_need_detail",
        org_fk("charging_need_detail", "need_id", "need", ondelete="CASCADE"),
        UniqueConstraint("need_id", name="uq_charging_need_detail_need"),
        CheckConstraint(
            "preferred_window_start IS NULL OR preferred_window_end IS NULL "
            "OR preferred_window_start <= preferred_window_end",
            name="ck_charging_detail_window"),
    )

    need_id: Mapped[str] = mapped_column(String(36), nullable=False)
    can_reach_site: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    access_assistance_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    preferred_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChargingDeviceRequest(TenantOwned, Base):
    __tablename__ = "charging_device_request"
    __table_args__ = org_scoped(
        "charging_device_request",
        org_fk("charging_device_request", "need_id", "need", ondelete="CASCADE"),
        check_in("charging_device_request", "device_type", DEVICE_TYPES),
        CheckConstraint("device_count > 0", name="ck_charging_device_count"),
    )

    need_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    device_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    connector_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    has_charger: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
