"""Privacy profile versions and policy versions (DB-010, DOM-030).

privacy_profile_version(id, organization_id, version, settings_json,
                        notice_version, activated_by_membership_id, activated_at)

The settings that storage enforces are real columns (not only JSON) so the
profile-constraint trigger (DB-023) can read them: names_allowed,
location_mode, gps_allowed, household_records_allowed. Once a version is
activated its settings are immutable (trigger in the migration); a change is
a new version.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TenantOwned, check_in, org_fk, org_scoped

PROFILE_KEYS = ("protective", "standard")
LOCATION_MODES = ("meeting_point", "address")
PROFILE_STATUSES = ("draft", "active", "retired")
PUBLIC_LEVELS = ("parish", "sector")
POLICY_KINDS = ("retention", "urgency", "vetting", "data_handling_statement", "other")

PLATFORM_MIN_K = 3


class PrivacyProfileVersion(TenantOwned, Base):
    __tablename__ = "privacy_profile_version"
    __table_args__ = org_scoped(
        "privacy_profile_version",
        org_fk("privacy_profile_version", "activated_by_membership_id",
               "organization_membership"),
        check_in("privacy_profile_version", "profile_key", PROFILE_KEYS),
        check_in("privacy_profile_version", "location_mode", LOCATION_MODES),
        check_in("privacy_profile_version", "status", PROFILE_STATUSES),
        check_in("privacy_profile_version", "public_level", PUBLIC_LEVELS),
        CheckConstraint(f"aggregate_k >= {PLATFORM_MIN_K}", name="ck_profile_aggregate_k"),
        CheckConstraint(f"public_k >= {PLATFORM_MIN_K}", name="ck_profile_public_k"),
        CheckConstraint("public_delay_hours >= 0", name="ck_profile_public_delay"),
        # GPS needs address mode; meeting-point mode never stores points.
        CheckConstraint("NOT gps_allowed OR location_mode = 'address'",
                        name="ck_profile_gps_needs_address"),
        CheckConstraint("status = 'draft' OR activated_at IS NOT NULL",
                        name="ck_profile_activated_at"),
        Index("uq_privacy_profile_version", "organization_id", "version", unique=True),
        # At most one active version per org.
        Index("uq_privacy_profile_active", "organization_id", unique=True,
              postgresql_where=text("status = 'active'"),
              sqlite_where=text("status = 'active'")),
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")

    names_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    location_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    gps_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    household_records_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contact_list_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # e.g. ["alias", "sector", "meeting_point", "phone"] or ["name", "address", "phone"]
    contact_list_fields: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Protective: phone kept only while follow-up consent exists, then N days.
    reporter_phone_retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reporter_key_rotation_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    report_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=548)
    aggregate_k: Mapped[int] = mapped_column(Integer, nullable=False)
    public_dashboard_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_level: Mapped[str] = mapped_column(String(16), nullable=False)
    public_k: Mapped[int] = mapped_column(Integer, nullable=False)
    public_delay_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    # Anything else the domain wants to version with the profile.
    settings_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    notice_version: Mapped[str] = mapped_column(String(32), nullable=False)
    activated_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optimistic version for drafts (DB-031).
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PolicyVersion(TenantOwned, Base):
    """Other versioned org policies (retention, urgency rules, statements)."""

    __tablename__ = "policy_version"
    __table_args__ = org_scoped(
        "policy_version",
        check_in("policy_version", "kind", POLICY_KINDS),
        Index("uq_policy_version", "organization_id", "kind", "version", unique=True),
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    body_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
