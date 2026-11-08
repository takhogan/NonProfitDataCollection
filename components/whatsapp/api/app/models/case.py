"""LEGACY cases and needs (household/case slice; DOM-090 deferred module).

Superseded by ``app.models.report.Need`` (table ``need``). The old ``need``
table was renamed to ``legacy_need`` by migration 2a7c4e91d3b0; ``case_record``
keeps its name. Kept until the api session migrates off it.


case_record(id, organization_id, household_id, campaign_id?, status,
            assigned_membership_id?, opened_at, closed_at?, closure_reason?)
need(id, organization_id, case_id, assessment_id, category, requested_quantity?,
     unit?, period_start?, period_end?, urgency, urgency_reasons,
     status, last_confirmed_at, supersedes_need_id?)

Needs are tracked separately and do not auto-close when one service is fulfilled.
Water is measured in liters; charging in device sessions (incompatible units).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgOwned, utcnow

CASE_STATUSES = ("open", "closed")
NEED_CATEGORIES = ("water_delivery", "charging_access")
NEED_UNITS = ("liters", "device_sessions")
NEED_STATUSES = ("requested", "allocated", "partially_fulfilled", "fulfilled", "withdrawn")
URGENCY_LEVELS = ("low", "routine", "urgent", "unknown")


class CaseRecord(OrgOwned, Base):
    __tablename__ = "case_record"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("household.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    assigned_membership_id: Mapped[str | None] = mapped_column(
        ForeignKey("organization_membership.id"), nullable=True, index=True
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    household: Mapped["Household"] = relationship(back_populates="cases")  # noqa: F821
    needs: Mapped[list["LegacyNeed"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class LegacyNeed(OrgOwned, Base):
    __tablename__ = "legacy_need"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_record.id"), nullable=False, index=True
    )
    assessment_id: Mapped[str | None] = mapped_column(
        ForeignKey("assessment.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    urgency: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    urgency_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_need_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    case: Mapped[CaseRecord] = relationship(back_populates="needs")


# Backwards-compatible import name for app.domain.intake (legacy).
Need = LegacyNeed
