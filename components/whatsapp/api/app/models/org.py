"""Organizations, users, and memberships.

organization(id, name, status)
user(id, auth_subject)  -- plus local auth fields for the hackathon
organization_membership(id, organization_id, user_id, role, status)
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk, org_fk

# Legacy household/case roles (still used by the hackathon API and seed users).
ROLES = ("volunteer", "caseworker", "reviewer", "coordinator", "administrator")

# Pilot roles (components/REQUIREMENTS.md "Roles"). "public" is not a
# membership role: it is the anonymous dashboard reader.
PILOT_ROLES = (
    "org_admin", "coordinator", "reviewer", "intake_volunteer", "provider", "analyst",
)
STAFF_ROLES = ("org_admin", "coordinator", "reviewer", "intake_volunteer")


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "user"

    # auth_subject is the stable external identity key (PLATFORM_PLAN.md).
    # For the hackathon it is the login email; password_hash backs JWT login.
    auth_subject: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OrganizationMembership(UUIDPk, Timestamps, Base):
    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        # Target for org-scoped composite FKs from pilot tables (DB-001).
        UniqueConstraint("organization_id", "id", name="uq_organization_membership_org_id"),
        org_fk("organization_membership", "provider_organization_id",
               "provider_organization", use_alter=True),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="caseworker")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    # Set for `provider` memberships: the provider organization the user acts for.
    provider_organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
