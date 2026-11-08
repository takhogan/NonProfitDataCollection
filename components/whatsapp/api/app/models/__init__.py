"""SQLAlchemy ORM models (maps to the components/database boundary).

Import all models here so Alembic autogenerate and Base.metadata see them.

Pilot report-centric model: privacy, geo, outreach, reporting, report,
provider, aggregate, quality, system. Legacy household/case slice (kept until
the api session migrates): household, intake (Assessment, LegacyObservation),
case (CaseRecord, LegacyNeed).
"""
from app.models.base import Base  # noqa: F401
from app.models.org import Organization, OrganizationMembership, User  # noqa: F401

# Legacy household/case slice.
from app.models.household import Household, HouseholdMember, Person  # noqa: F401
from app.models.intake import Assessment, LegacyObservation  # noqa: F401
from app.models.case import CaseRecord, LegacyNeed  # noqa: F401

from app.models.outbox import OutboundMessage  # noqa: F401  (WhatsApp step-1 outbox)
from app.models.channel import ChannelAccount  # noqa: F401  (phone_number_id -> org)

# Pilot model.
from app.models.privacy import PolicyVersion, PrivacyProfileVersion  # noqa: F401
from app.models.geo import Area, AreaAlias, AreaBoundary, MeetingPoint, OutageEpisode  # noqa: F401
from app.models.outreach import Campaign, CampaignArea, QuestionnaireVersion  # noqa: F401
from app.models.reporting import (  # noqa: F401
    ContactEndpoint, Conversation, Message, Permission, ReporterKey,
)
from app.models.report import (  # noqa: F401
    ChargingDeviceRequest, ChargingNeedDetail, Need, Observation, Report, ReportLocation,
    WaterNeedDetail,
)
from app.models.provider import (  # noqa: F401
    Activity, ActivityArea, AlertDelivery, AlertSubscription, AlertSubscriptionArea, ApiKey,
    Broadcast, BroadcastDelivery, ExportRecord, ProviderOrganization, ProviderScope, ShareEvent,
)
from app.models.aggregate import (  # noqa: F401
    CoverageCell, ExternalIndicator, IndicatorCell, IndicatorDirtyCell, PublicActivity,
    PublicIndicatorCell,
)
from app.models.quality import (  # noqa: F401
    DataJob, DataJobResult, DuplicateCandidate, MergeEvent, ObservationLink, ReviewDecision,
    ReviewTask,
)
from app.models.system import (  # noqa: F401
    AuditEvent, IdempotencyKey, InboundEvent, Job, MessageStatusEvent, OutboxMessage,
)
