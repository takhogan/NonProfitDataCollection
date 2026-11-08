"""Campaigns and questionnaires (DB-010)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TenantOwned, check_in, org_fk, org_scoped

CAMPAIGN_STATUSES = ("draft", "active", "paused", "ended")


class QuestionnaireVersion(TenantOwned, Base):
    __tablename__ = "questionnaire_version"
    __table_args__ = org_scoped(
        "questionnaire_version",
        Index("uq_questionnaire_version", "organization_id", "version", "language", unique=True),
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="es")
    definition_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)


class Campaign(TenantOwned, Base):
    __tablename__ = "campaign"
    __table_args__ = org_scoped(
        "campaign",
        org_fk("campaign", "questionnaire_version_id", "questionnaire_version"),
        check_in("campaign", "status", CAMPAIGN_STATUSES),
        CheckConstraint("ends_at IS NULL OR starts_at <= ends_at", name="ck_campaign_range"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Neutral per-campaign display identity, e.g. "Metron Reporter" (SEC-12).
    display_identity: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    questionnaire_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CampaignArea(TenantOwned, Base):
    __tablename__ = "campaign_area"
    __table_args__ = org_scoped(
        "campaign_area",
        org_fk("campaign_area", "campaign_id", "campaign", ondelete="CASCADE"),
        org_fk("campaign_area", "area_id", "area"),
        Index("uq_campaign_area", "organization_id", "campaign_id", "area_id", unique=True),
    )

    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False)
    area_id: Mapped[str] = mapped_column(String(36), nullable=False)
