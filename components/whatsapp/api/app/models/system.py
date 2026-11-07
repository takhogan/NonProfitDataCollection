"""System tables: idempotency keys and the raw WhatsApp inbound event inbox.

idempotency_key stores the result of a retryable mutation so an offline retry
returns the same response instead of creating duplicates.

inbound_event is the durable webhook inbox: the raw provider payload is persisted
before the request is acknowledged. A separate worker (later) polls unprocessed
rows. Provider message IDs are unique per channel account so replays do not
re-create work.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, utcnow


class IdempotencyKey(UUIDPk, Timestamps, Base):
    __tablename__ = "idempotency_key"
    __table_args__ = (
        # One stored result per (org, endpoint, client-supplied key).
        UniqueConstraint(
            "organization_id", "endpoint", "key", name="uq_idempotency"
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)


class InboundEvent(UUIDPk, Timestamps, Base):
    __tablename__ = "inbound_event"
    __table_args__ = (
        # Dedupe replayed provider deliveries per channel account.
        UniqueConstraint(
            "channel_account_id",
            "provider_message_id",
            name="uq_inbound_provider_msg",
        ),
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
