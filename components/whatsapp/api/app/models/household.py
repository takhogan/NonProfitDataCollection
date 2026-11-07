"""People, households, and household membership.

person(id, organization_id, preferred_name?, preferred_language?)
household(id, organization_id, reference_code, estimated_member_count?,
          current_location_id?)
household_member(id, organization_id, household_id, person_id,
                 relationship?, valid_from, valid_to?)

A shared phone is not a person identifier; individual member records are
optional (an estimated count can be enough). Contact endpoints / encrypted
addresses are deferred to a later deliverable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgOwned, utcnow


class Person(OrgOwned, Base):
    __tablename__ = "person"

    preferred_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    memberships: Mapped[list["HouseholdMember"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class Household(OrgOwned, Base):
    __tablename__ = "household"
    __table_args__ = (
        # reference_code is human-facing; unique within an organization only.
        UniqueConstraint("organization_id", "reference_code", name="uq_household_ref"),
    )

    reference_code: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_member_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_location_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    members: Mapped[list["HouseholdMember"]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    cases: Mapped[list["CaseRecord"]] = relationship(  # noqa: F821
        back_populates="household"
    )


class HouseholdMember(OrgOwned, Base):
    __tablename__ = "household_member"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("household.id"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id"), nullable=False, index=True
    )
    relationship_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    household: Mapped[Household] = relationship(back_populates="members")
    person: Mapped[Person] = relationship(back_populates="memberships")
