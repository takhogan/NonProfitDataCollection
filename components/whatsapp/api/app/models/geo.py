"""Geography: areas, aliases, versioned boundaries, meeting points (DB-060..062).

Areas are tenant-owned (each operating NGO holds its own copy of the
state -> municipality -> parish -> sector tree), so every report, need, and
activity reference is an org-scoped composite FK (DB-001).

Meeting points are public places (plaza, church, school, bodega) per sector.
They hold no personal data; ``public_point`` is the coordinate of the public
place, never a home. Deactivation keeps references (status ``inactive``).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base, GeoType, TenantOwned, check_in, org_fk, org_scoped,
)

AREA_TYPES = ("state", "municipality", "parish", "sector")
MEETING_POINT_KINDS = ("plaza", "church", "school", "bodega", "health_center",
                       "community_center", "other")
MEETING_POINT_STATUSES = ("active", "inactive")
SERVICE_TYPES = ("electricity", "piped_water")
OUTAGE_EPISODE_STATUSES = ("suspected", "confirmed", "ended", "dismissed")


class Area(TenantOwned, Base):
    __tablename__ = "area"
    __table_args__ = org_scoped(
        "area",
        org_fk("area", "parent_area_id", "area"),
        check_in("area", "type", AREA_TYPES),
        check_in("area", "status", ("active", "retired")),
        CheckConstraint("parent_area_id IS NULL OR parent_area_id <> id",
                        name="ck_area_not_own_parent"),
        Index("ix_area_org_parent", "organization_id", "parent_area_id"),
        Index("uq_area_code", "organization_id", "type", "official_code", unique=True),
    )

    parent_area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    official_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class AreaAlias(TenantOwned, Base):
    __tablename__ = "area_alias"
    __table_args__ = org_scoped(
        "area_alias",
        org_fk("area_alias", "area_id", "area", ondelete="CASCADE"),
        Index("uq_area_alias", "organization_id", "normalized_alias", "area_id", unique=True),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False)


class AreaBoundary(TenantOwned, Base):
    """Versioned boundary; the current one has ``valid_to IS NULL``."""

    __tablename__ = "area_boundary"
    __table_args__ = org_scoped(
        "area_boundary",
        org_fk("area_boundary", "area_id", "area", ondelete="CASCADE"),
        CheckConstraint("valid_to IS NULL OR valid_from <= valid_to",
                        name="ck_area_boundary_range"),
        Index("uq_area_boundary_version", "organization_id", "area_id", "version", unique=True),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    boundary: Mapped[str] = mapped_column(GeoType("MULTIPOLYGON", 4326), nullable=False)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MeetingPoint(TenantOwned, Base):
    __tablename__ = "meeting_point"
    __table_args__ = org_scoped(
        "meeting_point",
        org_fk("meeting_point", "area_id", "area"),
        check_in("meeting_point", "kind", MEETING_POINT_KINDS),
        check_in("meeting_point", "status", MEETING_POINT_STATUSES),
        Index("ix_meeting_point_org_area", "organization_id", "area_id", "status"),
    )

    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_point: Mapped[str | None] = mapped_column(GeoType("POINT", 4326), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class OutageEpisode(TenantOwned, Base):
    """Optional, correctable grouping by area and time (DOM-016)."""

    __tablename__ = "outage_episode"
    __table_args__ = org_scoped(
        "outage_episode",
        org_fk("outage_episode", "area_id", "area"),
        check_in("outage_episode", "service_type", SERVICE_TYPES),
        check_in("outage_episode", "status", OUTAGE_EPISODE_STATUSES),
        CheckConstraint("ended_at IS NULL OR started_at IS NULL OR started_at <= ended_at",
                        name="ck_outage_episode_range"),
    )

    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suspected")
    assessment_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
