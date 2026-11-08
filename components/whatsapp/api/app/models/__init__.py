"""SQLAlchemy ORM models (maps to the components/database boundary).

Import all models here so Alembic autogenerate and Base.metadata see them.
"""
from app.models.base import Base  # noqa: F401
from app.models.org import Organization, OrganizationMembership, User  # noqa: F401
from app.models.household import Household, HouseholdMember, Person  # noqa: F401
from app.models.intake import Assessment, Observation  # noqa: F401
from app.models.case import CaseRecord, Need  # noqa: F401
from app.models.system import IdempotencyKey, InboundEvent  # noqa: F401
from app.models.outbox import OutboundMessage  # noqa: F401
