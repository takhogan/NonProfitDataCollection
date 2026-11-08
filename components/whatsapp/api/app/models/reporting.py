"""Contacts, reporter keys, permissions, conversations, messages (DB-011).

- ``contact_endpoint.encrypted_address`` is ciphertext produced by the app
  (DB-050); ``address_lookup_hmac`` is an org-scoped HMAC (DB-051). Plain phone
  hashes are never stored.
- ``reporter_key`` is the pseudonymous key that links repeat reports
  (DOM-014). ``key_hmac`` = HMAC(org key, endpoint || epoch); rotating the
  epoch gives a new key. ``contact_endpoint_id`` is nulled when the phone is
  deleted under the profile's retention, which keeps aggregate history.
- ``permission`` holds one purpose-specific record per decision (DOM-060).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, Index, Integer, LargeBinary, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, check_in, org_fk, org_scoped

CHANNELS = ("whatsapp", "sms", "phone", "volunteer_assisted")
ENDPOINT_STATUSES = ("active", "opted_out", "deleted")
PERMISSION_PURPOSES = ("notice_ack", "refresh_prompts", "area_broadcasts", "contact_list")
PERMISSION_DECISIONS = ("granted", "denied")
MESSAGE_DIRECTIONS = ("inbound", "outbound")
DELIVERY_STATUSES = ("received", "queued", "sent", "delivered", "read", "failed")


class ContactEndpoint(TenantOwned, Base):
    __tablename__ = "contact_endpoint"
    __table_args__ = org_scoped(
        "contact_endpoint",
        check_in("contact_endpoint", "channel", CHANNELS),
        check_in("contact_endpoint", "status", ENDPOINT_STATUSES),
        # Deleted endpoints keep no address.
        CheckConstraint("status <> 'deleted' OR encrypted_address IS NULL",
                        name="ck_contact_endpoint_deleted_no_address"),
        UniqueConstraint("organization_id", "channel", "address_lookup_hmac",
                         name="uq_contact_endpoint_lookup"),
    )

    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_address: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    address_lookup_hmac: Mapped[str] = mapped_column(String(128), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReporterKey(TenantOwned, Base):
    __tablename__ = "reporter_key"
    __table_args__ = org_scoped(
        "reporter_key",
        # No ON DELETE SET NULL: it would null organization_id too. Retention
        # nulls contact_endpoint_id before deleting the endpoint.
        org_fk("reporter_key", "contact_endpoint_id", "contact_endpoint"),
        UniqueConstraint("organization_id", "key_hmac", name="uq_reporter_key_hmac"),
        Index("ix_reporter_key_endpoint", "organization_id", "contact_endpoint_id", "epoch"),
        CheckConstraint("expires_at IS NULL OR expires_at > created_at",
                        name="ck_reporter_key_expiry"),
    )

    key_hmac: Mapped[str] = mapped_column(String(128), nullable=False)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    contact_endpoint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Short display alias for protective contact lists, e.g. "Vecino-4F2".
    alias: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Permission(TenantOwned, Base):
    """Purpose-specific permission (DOM-060). Not RLS-readable by providers."""

    __tablename__ = "permission"
    __table_args__ = org_scoped(
        "permission",
        org_fk("permission", "reporter_key_id", "reporter_key", ondelete="CASCADE"),
        org_fk("permission", "contact_endpoint_id", "contact_endpoint", ondelete="CASCADE"),
        check_in("permission", "purpose", PERMISSION_PURPOSES),
        check_in("permission", "decision", PERMISSION_DECISIONS),
        CheckConstraint("reporter_key_id IS NOT NULL OR contact_endpoint_id IS NOT NULL",
                        name="ck_permission_subject"),
        CheckConstraint("withdrawn_at IS NULL OR withdrawn_at >= captured_at",
                        name="ck_permission_withdrawn_after_capture"),
        Index("ix_permission_subject", "organization_id", "reporter_key_id", "purpose"),
        Index("ix_permission_endpoint", "organization_id", "contact_endpoint_id", "purpose"),
    )

    reporter_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    contact_endpoint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Conversation(TenantOwned, Base):
    __tablename__ = "conversation"
    __table_args__ = org_scoped(
        "conversation",
        org_fk("conversation", "contact_endpoint_id", "contact_endpoint"),
        org_fk("conversation", "campaign_id", "campaign"),
        org_fk("conversation", "questionnaire_version_id", "questionnaire_version"),
        org_fk("conversation", "assigned_membership_id", "organization_membership"),
        Index("ix_conversation_endpoint", "organization_id", "contact_endpoint_id"),
    )

    contact_endpoint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    questionnaire_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    intake_state: Mapped[str] = mapped_column(String(64), nullable=False, default="start")
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Message(TenantOwned, Base):
    """A conversation message. Raw content lives in restricted storage only."""

    __tablename__ = "message"
    __table_args__ = org_scoped(
        "message",
        org_fk("message", "conversation_id", "conversation", ondelete="CASCADE"),
        check_in("message", "direction", MESSAGE_DIRECTIONS),
        check_in("message", "delivery_status", DELIVERY_STATUSES),
        # DB-025: provider message IDs are unique per channel account.
        UniqueConstraint("channel_account_id", "provider_message_id",
                         name="uq_message_provider_id"),
        Index("ix_message_conversation", "organization_id", "conversation_id"),
    )

    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    content_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
