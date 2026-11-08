"""LEGACY household/case intake slice: assessments and observations.

Superseded by the report-centric pilot model in ``app.models.report``
(``report``, ``observation``, ``need``). Kept so the hackathon API keeps working
until the api session migrates; the old ``observation`` table was renamed to
``legacy_observation`` by migration 2a7c4e91d3b0. Do not build new features on it.


assessment(id, organization_id, conversation_id?, source_message_id?,
           questionnaire_version_id, reporter_person_id?, household_id?,
           campaign_id?, source_channel, reporting_relationship,
           answers_json, submitted_at, confirmed_at?, supersedes_assessment_id?)
observation(id, organization_id, assessment_id, household_id?, location_id,
            service_zone_id?, outage_episode_id?, service_type, subject_scope,
            status, observation_start_at?, observation_end_at?, time_precision,
            reported_timezone, outage_started_at?, onset_precision?,
            source_kind, source_group_id?, supersedes_observation_id?)

Trimmed to the fields the intake slice needs; conversation/location/zone/episode
references are nullable and wired up in later deliverables. answers_json keeps the
original reporter answers; preserve, do not overwrite.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgOwned, utcnow

SERVICE_TYPES = ("electricity", "piped_water")
OBSERVATION_STATUSES = ("available", "unavailable", "intermittent", "unknown")
SOURCE_CHANNELS = ("whatsapp", "phone", "volunteer_assisted")
REPORTING_RELATIONSHIPS = ("self", "household", "other_person", "area")
SUBJECT_SCOPES = ("household", "area")


class Assessment(OrgOwned, Base):
    __tablename__ = "assessment"

    household_id: Mapped[str | None] = mapped_column(
        ForeignKey("household.id"), nullable=True, index=True
    )
    reporter_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True
    )
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    reporting_relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    answers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    observations: Mapped[list["LegacyObservation"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class LegacyObservation(OrgOwned, Base):
    __tablename__ = "legacy_observation"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment.id"), nullable=False, index=True
    )
    household_id: Mapped[str | None] = mapped_column(
        ForeignKey("household.id"), nullable=True, index=True
    )
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="household")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    observation_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    reported_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Caracas")
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="firsthand")
    supersedes_observation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="observations")


# Backwards-compatible import name for app.domain.intake (legacy).
Observation = LegacyObservation
