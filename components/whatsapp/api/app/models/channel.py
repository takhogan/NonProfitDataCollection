"""WhatsApp channel accounts: which organization owns a Meta phone number.

Read by the worker before any tenant context exists (it is how an inbound event
finds its tenant, OPW-005), so this table is not row-level secured. Runtime
roles may only SELECT it; link numbers with ``python -m scripts.link_channel``.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk

CHANNEL_ACCOUNT_STATUSES = ("active", "disabled")


class ChannelAccount(UUIDPk, Timestamps, Base):
    __tablename__ = "channel_account"
    __table_args__ = (
        UniqueConstraint("phone_number_id", name="uq_channel_account_phone_number_id"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_channel_account_status"),
    )

    phone_number_id: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization.id"), nullable=False
    )
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
