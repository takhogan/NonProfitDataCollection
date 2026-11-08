"""Provider organizations, activities, alerts, API keys, sharing (DB-012).

``share_event``, ``export_record`` and ``alert_delivery`` are append-only for
runtime roles (DB-022). Providers never read ``report``, ``contact_endpoint``,
``permission`` or ``review_*``; they read the ``v_indicator_cell``,
``v_coverage_cell``, ``v_activity`` views and, if vetted, ``provider_contact_list``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    AppendOnly, Base, JSONType, TenantOwned, check_in, org_fk, org_scoped, utcnow,
)
from app.models.report import NEED_CATEGORIES

VETTING_STATUSES = ("unvetted", "vetted", "suspended")
ACTIVITY_TYPES = ("water_distribution_point", "water_delivery", "charging_point", "other")
ACTIVITY_STATUSES = ("planned", "active", "paused", "ended")
ACTIVITY_VISIBILITY = ("tenant", "internal", "public")
CAPACITY_UNITS = ("liters_per_day", "devices_per_day")
ALERT_TRIGGERS = ("new_urgent_needs", "active_needs_above", "area_uncovered",
                  "external_outage_signal")
ALERT_CHANNELS = ("email", "whatsapp", "in_app")
EXPORT_KINDS = ("aggregate", "contact_list", "activity")
BROADCAST_STATUSES = ("draft", "approved", "sending", "sent", "cancelled")


class ProviderOrganization(TenantOwned, Base):
    __tablename__ = "provider_organization"
    __table_args__ = org_scoped(
        "provider_organization",
        org_fk("provider_organization", "vetting_changed_by_membership_id",
               "organization_membership"),
        check_in("provider_organization", "vetting_status", VETTING_STATUSES),
        UniqueConstraint("organization_id", "name", name="uq_provider_organization_name"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vetting_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unvetted")
    vetting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    vetting_changed_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vetting_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Reference to the responsible contact (a membership or encrypted record), not PII.
    responsible_contact_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    statement_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    may_disclose_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProviderScope(TenantOwned, Base):
    """Areas x categories a provider works in; bounds the contact list (DOM-054)."""

    __tablename__ = "provider_scope"
    __table_args__ = org_scoped(
        "provider_scope",
        org_fk("provider_scope", "provider_organization_id", "provider_organization",
               ondelete="CASCADE"),
        org_fk("provider_scope", "area_id", "area"),
        check_in("provider_scope", "category", NEED_CATEGORIES),
        UniqueConstraint("organization_id", "provider_organization_id", "area_id", "category",
                         name="uq_provider_scope"),
    )

    provider_organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)


class Activity(TenantOwned, Base):
    __tablename__ = "activity"
    __table_args__ = org_scoped(
        "activity",
        org_fk("activity", "provider_organization_id", "provider_organization"),
        org_fk("activity", "public_meeting_point_id", "meeting_point"),
        org_fk("activity", "created_by_membership_id", "organization_membership"),
        check_in("activity", "type", ACTIVITY_TYPES),
        check_in("activity", "category", NEED_CATEGORIES),
        check_in("activity", "status", ACTIVITY_STATUSES),
        check_in("activity", "visibility", ACTIVITY_VISIBILITY),
        check_in("activity", "capacity_unit", CAPACITY_UNITS, nullable=True),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR starts_at <= ends_at",
                        name="ck_activity_range"),
        CheckConstraint("capacity IS NULL OR (capacity >= 0 AND capacity_unit IS NOT NULL)",
                        name="ck_activity_capacity"),
        CheckConstraint(
            "capacity_unit IS NULL OR (capacity_unit = 'liters_per_day' "
            "AND category IN ('water_drinking', 'water_other')) "
            "OR (capacity_unit = 'devices_per_day' AND category = 'charging')",
            name="ck_activity_capacity_unit_category"),
        Index("ix_activity_org_status", "organization_id", "category", "status"),
        Index("ix_activity_provider", "organization_id", "provider_organization_id"),
    )

    provider_organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # {"kind": "one_off"|"recurring", "days": [...], "hours": [["08:00","12:00"]], "tz": ...}
    schedule_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    capacity_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Public location: a meeting point or a public-site description; never a household.
    public_meeting_point_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    public_location_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="tenant")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ActivityArea(TenantOwned, Base):
    __tablename__ = "activity_area"
    __table_args__ = org_scoped(
        "activity_area",
        org_fk("activity_area", "activity_id", "activity", ondelete="CASCADE"),
        org_fk("activity_area", "area_id", "area"),
        UniqueConstraint("organization_id", "activity_id", "area_id", name="uq_activity_area"),
        Index("ix_activity_area_area", "organization_id", "area_id"),
    )

    activity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    area_id: Mapped[str] = mapped_column(String(36), nullable=False)


class AlertSubscription(TenantOwned, Base):
    __tablename__ = "alert_subscription"
    __table_args__ = org_scoped(
        "alert_subscription",
        org_fk("alert_subscription", "membership_id", "organization_membership",
               ondelete="CASCADE"),
        check_in("alert_subscription", "category", NEED_CATEGORIES),
        check_in("alert_subscription", "trigger", ALERT_TRIGGERS),
        check_in("alert_subscription", "channel", ALERT_CHANNELS),
        CheckConstraint("threshold IS NULL OR threshold >= 0", name="ck_alert_threshold"),
        CheckConstraint("trigger <> 'active_needs_above' OR threshold IS NOT NULL",
                        name="ck_alert_threshold_required"),
        CheckConstraint("window_hours > 0", name="ck_alert_window"),
    )

    membership_id: Mapped[str] = mapped_column(String(36), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="in_app")
    window_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AlertSubscriptionArea(TenantOwned, Base):
    """The subscription's area set, as rows so each area is an org-scoped FK."""

    __tablename__ = "alert_subscription_area"
    __table_args__ = org_scoped(
        "alert_subscription_area",
        org_fk("alert_subscription_area", "alert_subscription_id", "alert_subscription",
               ondelete="CASCADE"),
        org_fk("alert_subscription_area", "area_id", "area"),
        UniqueConstraint("organization_id", "alert_subscription_id", "area_id",
                         name="uq_alert_subscription_area"),
    )

    alert_subscription_id: Mapped[str] = mapped_column(String(36), nullable=False)
    area_id: Mapped[str] = mapped_column(String(36), nullable=False)


class AlertDelivery(AppendOnly, TenantOwned, Base):
    """Aggregate-only alert, deduplicated per subscription per window (DOM-055)."""

    __tablename__ = "alert_delivery"
    __table_args__ = org_scoped(
        "alert_delivery",
        org_fk("alert_delivery", "alert_subscription_id", "alert_subscription"),
        check_in("alert_delivery", "channel", ALERT_CHANNELS),
        UniqueConstraint("organization_id", "alert_subscription_id", "window_start",
                         "trigger_key", name="uq_alert_delivery_window"),
    )

    alert_subscription_id: Mapped[str] = mapped_column(String(36), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    # Suppressed aggregate numbers only; never contact data.
    payload_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    outbox_reference: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ApiKey(TenantOwned, Base):
    """API key: only a hash is stored. Looked up by hash before tenant context
    is known, via the ``app.api_key_hash`` RLS escape (see db.lookup_api_key)."""

    __tablename__ = "api_key"
    __table_args__ = org_scoped(
        "api_key",
        org_fk("api_key", "membership_id", "organization_membership", ondelete="CASCADE"),
        org_fk("api_key", "provider_organization_id", "provider_organization"),
        UniqueConstraint("key_hash", name="uq_api_key_hash"),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at",
                        name="ck_api_key_revoked"),
    )

    membership_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider_organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExportRecord(AppendOnly, TenantOwned, Base):
    __tablename__ = "export_record"
    __table_args__ = org_scoped(
        "export_record",
        org_fk("export_record", "membership_id", "organization_membership"),
        org_fk("export_record", "provider_organization_id", "provider_organization"),
        org_fk("export_record", "api_key_id", "api_key"),
        check_in("export_record", "kind", EXPORT_KINDS),
        CheckConstraint("row_count >= 0", name="ck_export_record_rows"),
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filters_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watermark: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    object_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ShareEvent(AppendOnly, TenantOwned, Base):
    """One row per reporter shown/exported to a provider (DOM-054, DB-033)."""

    __tablename__ = "share_event"
    __table_args__ = org_scoped(
        "share_event",
        org_fk("share_event", "provider_organization_id", "provider_organization"),
        org_fk("share_event", "reporter_key_id", "reporter_key"),
        org_fk("share_event", "export_record_id", "export_record"),
        Index("ix_share_event_reporter", "organization_id", "reporter_key_id", "occurred_at"),
        Index("ix_share_event_provider", "organization_id", "provider_organization_id",
              "occurred_at"),
    )

    provider_organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # "membership:<id>" or "api_key:<id>"
    actor_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    reporter_key_id: Mapped[str] = mapped_column(String(36), nullable=False)
    fields_shared: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    export_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Broadcast(TenantOwned, Base):
    __tablename__ = "broadcast"
    __table_args__ = org_scoped(
        "broadcast",
        org_fk("broadcast", "activity_id", "activity"),
        org_fk("broadcast", "approved_by_membership_id", "organization_membership"),
        check_in("broadcast", "status", BROADCAST_STATUSES),
        CheckConstraint("status NOT IN ('approved', 'sending', 'sent') "
                        "OR approved_by_membership_id IS NOT NULL",
                        name="ck_broadcast_approved"),
        CheckConstraint("recipient_count >= 0", name="ck_broadcast_recipients"),
    )

    activity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_params: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    approved_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BroadcastDelivery(TenantOwned, Base):
    """Counts only: no per-recipient rows (DB-012)."""

    __tablename__ = "broadcast_delivery"
    __table_args__ = org_scoped(
        "broadcast_delivery",
        org_fk("broadcast_delivery", "broadcast_id", "broadcast", ondelete="CASCADE"),
        CheckConstraint("queued_count >= 0 AND delivered_count >= 0 AND blocked_count >= 0 "
                        "AND failed_count >= 0", name="ck_broadcast_delivery_counts"),
    )

    broadcast_id: Mapped[str] = mapped_column(String(36), nullable=False)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
