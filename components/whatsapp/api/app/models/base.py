"""Declarative base and shared column mixins.

Per PLATFORM_PLAN.md: operational records carry organization_id, created_at,
updated_at. IDs are UUIDs (stored as 36-char strings so the same models run on
SQLite locally and PostgreSQL in production).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDPk:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class OrgOwned(UUIDPk, Timestamps):
    """Mixin for tenant-owned operational records."""

    organization_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
