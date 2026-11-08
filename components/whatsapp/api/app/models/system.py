"""System tables: idempotency, webhook inbox, job queue, outbox, audit.

idempotency_key stores the result of a retryable mutation so an offline retry
returns the same response instead of creating duplicates (DB-030).

inbound_event is the durable webhook inbox: the raw provider payload is persisted
before the request is acknowledged. A worker polls unprocessed rows. Provider
message IDs are unique per channel account so replays do not re-create work.
It has no tenant until routed, so it is NOT row-level-secured; the runtime
role may only INSERT it and the worker role processes it (DB-004).

job is the operational queue (DB-034): claimed with FOR UPDATE SKIP LOCKED
(``app.db.claim_jobs``), with lease expiry, attempts, and next-run time.
Payloads carry IDs only, never tenant data, so job-table access grants no
tenant data. ``outbox_message`` *is* tenant data (RLS-forced).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    AppendOnly, Base, JSONType, TenantOwned, Timestamps, UUIDPk, check_in, org_fk,
    org_scoped, utcnow,
)

INBOUND_STATUSES = ("received", "processed", "ignored", "failed", "quarantined")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "dead")
OUTBOX_PURPOSES = ("conversation_reply", "refresh_prompt", "area_broadcast", "alert",
                   "opt_out_confirmation", "notice")
OUTBOX_STATUSES = ("pending", "sending", "sent", "blocked", "failed")


class IdempotencyKey(UUIDPk, Timestamps, Base):
    __tablename__ = "idempotency_key"
    __table_args__ = (
        # One stored result per (org, actor scope, operation, client key) (DB-030).
        UniqueConstraint(
            "organization_id", "actor_scope", "endpoint", "key", name="uq_idempotency"
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # e.g. "membership:<id>" or "api_key:<id>"; "" for legacy rows.
    actor_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="",
                                             server_default="")
    # Operation name (legacy column name kept for the hackathon API).
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Kept >= 30 days.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InboundEvent(UUIDPk, Timestamps, Base):
    __tablename__ = "inbound_event"
    __table_args__ = (
        # Dedupe replayed provider deliveries per channel account.
        UniqueConstraint(
            "channel_account_id",
            "provider_message_id",
            name="uq_inbound_provider_msg",
        ),
        Index("ix_inbound_event_pending", "status", "received_at"),
    )

    # Routed by payload kind: "message" or "status".
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    channel_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    # Pilot additions: routing + processing state. organization_id is set once
    # the channel account is resolved to a tenant.
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received",
                                        server_default="received")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw payload retention (NFR-09: 30 days); worker purges payload after this.
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageStatusEvent(UUIDPk, Base):
    """Deduplicated delivery-status events; may arrive repeated/out of order (DB-025)."""

    __tablename__ = "message_status_event"
    __table_args__ = (
        UniqueConstraint("channel_account_id", "provider_message_id", "status",
                         name="uq_message_status_event"),
    )

    channel_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  default=utcnow)


class Job(UUIDPk, Timestamps, Base):
    __tablename__ = "job"
    __table_args__ = (
        check_in("job", "status", JOB_STATUSES),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_job_attempts"),
        UniqueConstraint("dedupe_key", name="uq_job_dedupe_key"),
        Index("ix_job_claim", "status", "run_after", "priority"),
    )

    # Tenant the job acts for; the worker opens a tenant transaction with it.
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # IDs and parameters only; never personal data.
    payload_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=utcnow)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxMessage(TenantOwned, Base):
    """Outbound intent with a declared purpose (DOM-061). Sent by the worker
    outside any DB transaction; recipient is an endpoint reference."""

    __tablename__ = "outbox_message"
    __table_args__ = org_scoped(
        "outbox_message",
        org_fk("outbox_message", "contact_endpoint_id", "contact_endpoint"),
        org_fk("outbox_message", "conversation_id", "conversation"),
        check_in("outbox_message", "purpose", OUTBOX_PURPOSES),
        check_in("outbox_message", "status", OUTBOX_STATUSES),
        UniqueConstraint("organization_id", "dedupe_key", name="uq_outbox_dedupe"),
        Index("ix_outbox_pending", "organization_id", "status", "next_attempt_at"),
    )

    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    contact_endpoint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    template_params: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    body_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    block_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                      default=utcnow)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(AppendOnly, TenantOwned, Base):
    """Append-only, redacted audit (DB-053). No phone numbers, raw messages, or
    precise coordinates in ``redacted_change_summary``."""

    __tablename__ = "audit_event"
    __table_args__ = org_scoped(
        "audit_event",
        Index("ix_audit_event_org_time", "organization_id", "occurred_at"),
        Index("ix_audit_event_entity", "organization_id", "entity_type", "entity_id"),
    )

    actor_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  default=utcnow)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    redacted_change_summary: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
