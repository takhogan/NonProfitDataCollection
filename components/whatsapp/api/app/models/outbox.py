"""Transactional outbox for outbound WhatsApp messages.

The worker writes an OutboundMessage in the SAME transaction as the state change
that caused it (e.g. marking an inbound_event processed). A separate sender loop
then claims queued rows, sends them via the WhatsApp adapter, stores the returned
provider message id, and retries transient failures with bounded attempts.

Delivery-status webhooks (sent/delivered/read/failed) update the matching row by
its provider_message_id. We never claim exactly-once network delivery; the
provider message id plus status reconciliation is how we avoid blind resends.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk

# Lifecycle: queued -> sent -> (delivered|read) ; or queued -> failed.
OUTBOX_STATUSES = ("queued", "sent", "delivered", "read", "failed")


class OutboundMessage(UUIDPk, Timestamps, Base):
    __tablename__ = "outbound_message"

    # organization_id is nullable for Step 1 (no org resolution yet); Step 2's
    # conversation flow sets it. Kept here so the table is tenant-aware from day one.
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # The WhatsApp phone_number_id we send FROM (from the inbound payload metadata)
    # and the recipient wa_id / phone we send TO (the inbound message's `from`).
    phone_number_id: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Populated after a successful send; links delivery-status events back to us.
    provider_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dedupe key: at most one reply per inbound event (set by the worker). Lets a
    # replayed inbound event avoid queueing a second identical reply.
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
