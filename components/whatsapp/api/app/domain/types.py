"""Framework-free value types for the report-centric aggregation domain.

These frozen dataclasses and enums are the domain's own inputs and outputs. They
mirror the names in components/contracts (CON-*) and components/domain (DOM-*) so
that adapting them to the Pydantic contracts and SQLAlchemy models is mechanical:
one field here maps to one field there.

Conventions (DOM-005 / CON-003):
- ``None`` on an optional input means "not asked" / absent.
- Tri-state values use an explicit ``unknown`` enum member, never ``None``/0/False.
- On aggregate outputs, ``None`` on a count means "unknown or suppressed"; it is
  never a stand-in for zero.
- Liters are ``Decimal``; people and devices are ``int``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class Role(StrEnum):
    org_admin = "org_admin"
    coordinator = "coordinator"
    reviewer = "reviewer"
    intake_volunteer = "intake_volunteer"
    provider = "provider"
    analyst = "analyst"


@dataclass(frozen=True)
class DomainContext:
    """DOM-001: explicit org/actor/roles; never taken from a payload."""

    org_id: str
    actor_id: str
    roles: frozenset[Role]
    operation_key: Optional[str] = None
    provider_org_id: Optional[str] = None  # set for provider users

    def has(self, role: Role) -> bool:
        return role in self.roles


# ---------------------------------------------------------------------------
# Privacy profile (DOM-030..033)
# ---------------------------------------------------------------------------


class ProfileKind(StrEnum):
    protective = "protective"
    standard = "standard"
    custom = "custom"  # individually adjusted within platform minimums


class LocationMode(StrEnum):
    meeting_point = "meeting_point"
    address = "address"


class AreaLevel(StrEnum):
    state = "state"
    municipality = "municipality"
    parish = "parish"
    sector = "sector"


# Coarse → fine. A larger index is a finer level.
AREA_LEVEL_ORDER: tuple[AreaLevel, ...] = (
    AreaLevel.state,
    AreaLevel.municipality,
    AreaLevel.parish,
    AreaLevel.sector,
)


class ContactField(StrEnum):
    """Fields a contact-list row may carry (CON-015)."""

    alias = "alias"
    sector = "sector"
    meeting_point = "meeting_point"
    name = "name"
    address = "address"
    phone = "phone"


@dataclass(frozen=True)
class PrivacyProfile:
    """A versioned org policy (DOM-030). Every command reads the active version."""

    org_id: str
    version: int
    kind: ProfileKind
    notice_version: str
    names_allowed: bool
    location_mode: LocationMode
    gps_allowed: bool
    # None = kept per the general retention policy; an int = delete N days after the
    # last activity when the reporter has not consented to follow-ups.
    reporter_phone_retention_days: Optional[int]
    household_records_allowed: bool
    contact_list_enabled: bool
    contact_list_fields: frozenset[ContactField]
    reporter_key_rotation_days: int
    aggregate_k: int
    public_dashboard_enabled: bool
    public_level: AreaLevel
    public_k: int
    public_delay: timedelta
    activated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Areas and meeting points
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Area:
    id: str
    level: AreaLevel
    name: str
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class MeetingPoint:
    """DOM-034: a public place per sector; holds no personal data."""

    id: str
    sector_id: str
    name: str
    type: str
    description: str
    active: bool = True


# ---------------------------------------------------------------------------
# Reports, observations, needs (DOM-010..023)
# ---------------------------------------------------------------------------


class Channel(StrEnum):
    whatsapp = "whatsapp"
    assisted_intake = "assisted_intake"


class Relationship(StrEnum):
    self = "self"
    household = "household"
    other_person = "other_person"
    area = "area"


class ReportState(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    abandoned = "abandoned"
    superseded = "superseded"


class Service(StrEnum):
    electricity = "electricity"
    piped_water = "piped_water"


class ServiceStatus(StrEnum):
    available = "available"
    unavailable = "unavailable"
    intermittent = "intermittent"
    unknown = "unknown"


class TimePrecision(StrEnum):
    exact = "exact"
    approximate = "approximate"
    day = "day"
    unknown = "unknown"


class NeedCategory(StrEnum):
    water_drinking = "water_drinking"
    water_other = "water_other"
    charging = "charging"


class Unit(StrEnum):
    liters = "liters"
    people = "people"
    devices = "devices"


class RemainingSupply(StrEnum):
    none = "none"
    little = "little"
    some = "some"
    unknown = "unknown"


class Urgency(StrEnum):
    """Stated urgency, stored as reported (DOM-023)."""

    urgent = "urgent"
    soon = "soon"
    can_wait = "can_wait"
    unknown = "unknown"


class NeedState(StrEnum):
    active = "active"
    stale = "stale"
    resolved_by_reporter = "resolved_by_reporter"
    withdrawn = "withdrawn"
    expired = "expired"


OPEN_NEED_STATES = frozenset({NeedState.active, NeedState.stale})


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: Unit


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class MeetingPointLocation:
    """LocationDetail variant ``meeting_point`` (CON-010)."""

    meeting_point_id: Optional[str] = None
    none_nearby: bool = False


@dataclass(frozen=True)
class AddressLocation:
    """LocationDetail variant ``address`` (CON-010). Text is ciphertext at rest."""

    address_encrypted: Optional[str] = None
    landmark_encrypted: Optional[str] = None
    point: Optional[GeoPoint] = None


LocationDetail = MeetingPointLocation | AddressLocation


@dataclass(frozen=True)
class ObservationInput:
    service: Service
    status: ServiceStatus
    observed_at: datetime
    observed_precision: TimePrecision = TimePrecision.exact
    outage_onset: Optional[datetime] = None
    onset_precision: TimePrecision = TimePrecision.unknown


@dataclass(frozen=True)
class NeedInput:
    category: NeedCategory
    stated_urgency: Urgency = Urgency.unknown
    remaining_supply: RemainingSupply = RemainingSupply.unknown
    people_affected: Optional[int] = None
    quantity: Optional[Quantity] = None
    access_notes: tuple[str, ...] = ()
    preferred_times: tuple[str, ...] = ()


class PermissionPurpose(StrEnum):
    """DOM-060 / SEC-16: separate, withdrawable permissions."""

    notice_ack = "notice_ack"
    refresh_prompts = "refresh_prompts"
    area_broadcasts = "area_broadcasts"
    contact_list = "contact_list"


@dataclass(frozen=True)
class ReportSubmission:
    """Input to submitReport (DOM-010 / CON-010)."""

    channel: Channel
    relationship: Relationship
    area_id: str
    questionnaire_version: str
    notice_version: str
    location: Optional[LocationDetail] = None
    observations: tuple[ObservationInput, ...] = ()
    needs: tuple[NeedInput, ...] = ()
    permissions: frozenset[PermissionPurpose] = frozenset()
    # Profile-dependent personal fields; validated by profiles.validate_submission.
    reporter_name_encrypted: Optional[str] = None
    household_ref: Optional[str] = None
    source_digest: Optional[str] = None  # hash of forwarded text (DOM-017)


@dataclass(frozen=True)
class Observation:
    id: str
    report_id: str
    service: Service
    status: ServiceStatus
    observed_at: datetime
    observed_precision: TimePrecision
    outage_onset: Optional[datetime]
    onset_precision: TimePrecision


@dataclass(frozen=True)
class Need:
    id: str
    report_id: str
    category: NeedCategory
    state: NeedState
    stated_urgency: Urgency
    remaining_supply: RemainingSupply
    created_at: datetime
    last_confirmed_at: datetime
    people_affected: Optional[int] = None
    quantity: Optional[Quantity] = None
    access_notes: tuple[str, ...] = ()
    preferred_times: tuple[str, ...] = ()
    state_changed_at: Optional[datetime] = None
    refresh_prompts_sent: int = 0
    last_prompted_at: Optional[datetime] = None
    linked_need_id: Optional[str] = None  # prior need of the same reporter (DOM-014)
    # Set when a repeat report from the same reporter key carries this category
    # again: the newer need is the reporter's current state. A link, not a state.
    replaced_by_id: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_NEED_STATES and self.replaced_by_id is None


class Disposition(StrEnum):
    valid = "valid"
    duplicate = "duplicate"
    spam = "spam"
    location_corrected = "location_corrected"
    unresolved = "unresolved"


EXCLUDING_DISPOSITIONS = frozenset({Disposition.duplicate, Disposition.spam})


@dataclass(frozen=True)
class Report:
    id: str
    org_id: str
    channel: Channel
    relationship: Relationship
    area_id: str
    state: ReportState
    profile_version: int
    notice_version: str
    questionnaire_version: str
    submitted_at: datetime
    reporter_key: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    location: Optional[LocationDetail] = None
    observations: tuple[Observation, ...] = ()
    needs: tuple[Need, ...] = ()
    permissions: frozenset[PermissionPurpose] = frozenset()
    reporter_name_encrypted: Optional[str] = None
    household_ref: Optional[str] = None
    source_digest: Optional[str] = None
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    # Review outcome (DOM-072). Only a human disposition sets these.
    disposition: Optional[Disposition] = None
    duplicate_of_id: Optional[str] = None
    exclusion_reason: Optional[str] = None
    pending_review: bool = False
    urgent_flagged: bool = False


# ---------------------------------------------------------------------------
# Indicators (DOM-040..046)
# ---------------------------------------------------------------------------


class Bucket(StrEnum):
    h6 = "6h"
    h24 = "24h"
    d7 = "7d"

    @property
    def duration(self) -> timedelta:
        return {
            Bucket.h6: timedelta(hours=6),
            Bucket.h24: timedelta(hours=24),
            Bucket.d7: timedelta(days=7),
        }[self]


Subject = NeedCategory | Service


class CoverageLabel(StrEnum):
    none = "none"
    thin = "thin"
    reported = "reported"


class ConfidenceLabel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ExternalAgreement(StrEnum):
    agrees = "agrees"
    disagrees = "disagrees"
    no_data = "no_data"


@dataclass(frozen=True)
class ExternalContext:
    """A separate evidence layer (DOM-045/074). Never changes report counts."""

    area_id: str
    service: Service
    source: str  # e.g. "monitor_ciudad", "ntl_radiance_anomaly"
    status: ServiceStatus
    observed_at: datetime
    large_outage: bool = False


@dataclass(frozen=True)
class Confidence:
    label: ConfidenceLabel
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IndicatorCell:
    """CON-012. Counts are ``None`` when unknown (coverage none) or suppressed."""

    area_id: str
    level: AreaLevel
    subject: Subject
    bucket: Bucket
    bucket_start: datetime
    bucket_end: datetime
    coverage: CoverageLabel
    confidence: Confidence
    suppressed: bool
    merged_into_area_id: Optional[str]
    active_needs: Optional[int]
    urgent_active_needs: Optional[int]
    distinct_reporters: Optional[int]
    distinct_households: Optional[int]  # None unless the profile allows households
    people_affected_known: Optional[int]
    people_affected_unknown_count: Optional[int]
    urgency_mix: Optional[Mapping[Urgency, int]]
    supply_mix: Optional[Mapping[RemainingSupply, int]]
    status_mix: Optional[Mapping[ServiceStatus, int]]
    freshness: Optional[datetime]
    oldest_active_need_at: Optional[datetime]
    pending_review_share: Optional[float]
    unit_label: str  # "reportantes" (protective) or "hogares" (standard)
    method_version: str
    input_watermark: Optional[str]


@dataclass(frozen=True)
class IndicatorSnapshot:
    """DOM-046: everything needed to explain a published number later."""

    org_id: str
    bucket: Bucket
    bucket_end: datetime
    method_version: str
    profile_version: int
    input_watermark: Optional[str]
    computed_at: datetime
    cells: tuple[IndicatorCell, ...]


@dataclass(frozen=True)
class AreaOfNeed:
    """CON-013: a cell plus rank and the criteria used."""

    cell: IndicatorCell
    rank: int
    criteria: tuple[str, ...]
    method_version: str


# ---------------------------------------------------------------------------
# Providers (DOM-050..055)
# ---------------------------------------------------------------------------


class VettingStatus(StrEnum):
    unvetted = "unvetted"
    vetted = "vetted"
    suspended = "suspended"


@dataclass(frozen=True)
class ProviderOrganization:
    id: str
    org_id: str
    name: str
    vetting: VettingStatus
    scope_area_ids: frozenset[str]
    scope_categories: frozenset[NeedCategory]
    statement_version: Optional[str] = None
    responsible_contact_id: Optional[str] = None
    name_in_broadcasts_allowed: bool = False
    version: int = 1


class ActivityType(StrEnum):
    water_distribution_point = "water_distribution_point"
    water_delivery = "water_delivery"
    charging_point = "charging_point"
    other = "other"


class ActivityStatus(StrEnum):
    planned = "planned"
    active = "active"
    paused = "paused"
    ended = "ended"


class ActivityDisplayStatus(StrEnum):
    planned = "planned"
    active = "active"
    paused = "paused"
    ended = "ended"
    unconfirmed = "unconfirmed"


class Visibility(StrEnum):
    tenant = "tenant"  # all providers in the tenant see details
    internal_only = "internal_only"  # counts toward coverage; details hidden
    public = "public"  # also on the public dashboard (DOM-081)


@dataclass(frozen=True)
class Schedule:
    recurring: bool
    description: str  # e.g. "sáb 8–12"
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


@dataclass(frozen=True)
class Activity:
    id: str
    provider_id: str
    type: ActivityType
    category: NeedCategory
    area_ids: frozenset[str]
    schedule: Schedule
    status: ActivityStatus
    last_confirmed_at: datetime
    visibility: Visibility = Visibility.tenant
    capacity: Optional[Quantity] = None
    public_location_id: Optional[str] = None  # meeting point / public site only
    version: int = 1


class CoverageStatus(StrEnum):
    covered = "covered"
    uncovered = "uncovered"
    unknown = "unknown"


@dataclass(frozen=True)
class CoverageCell:
    area_id: str
    category: NeedCategory
    status: CoverageStatus
    activity_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ReporterContact:
    """Profile-filtered contact details held for a reporter key."""

    reporter_key: str
    phone_encrypted: Optional[str] = None
    alias: Optional[str] = None
    name_encrypted: Optional[str] = None
    address_encrypted: Optional[str] = None


@dataclass(frozen=True)
class Permission:
    reporter_key: str
    purpose: PermissionPurpose
    notice_version: str
    granted_at: datetime
    withdrawn_at: Optional[datetime] = None

    def active_at(self, now: datetime) -> bool:
        return self.granted_at <= now and (self.withdrawn_at is None or self.withdrawn_at > now)


@dataclass(frozen=True)
class ContactListRow:
    """CON-015. Only the fields the profile allows are populated."""

    profile_kind: ProfileKind
    reporter_key: str
    need_id: str
    category: NeedCategory
    urgency: Urgency
    preferred_times: tuple[str, ...]
    phone_encrypted: Optional[str] = None
    alias: Optional[str] = None
    sector_id: Optional[str] = None
    meeting_point_id: Optional[str] = None
    name_encrypted: Optional[str] = None
    address_encrypted: Optional[str] = None


@dataclass(frozen=True)
class ShareEvent:
    provider_id: str
    actor_id: str
    reporter_key: str
    need_id: str
    at: datetime
    purpose: str = "contact_list_view"


class AlertTrigger(StrEnum):
    new_urgent_needs = "new_urgent_needs"
    active_needs_above = "active_needs_above"
    area_uncovered = "area_uncovered"
    external_outage = "external_outage"


@dataclass(frozen=True)
class AlertSubscription:
    id: str
    provider_id: str
    user_id: str
    area_ids: frozenset[str]
    category: NeedCategory
    trigger: AlertTrigger
    threshold: Optional[int] = None  # N for active_needs_above
    dedup_window: timedelta = timedelta(hours=6)
    active: bool = True


@dataclass(frozen=True)
class Alert:
    """CON-014: aggregate fields only — no reporter, contact or report IDs."""

    subscription_id: str
    trigger: AlertTrigger
    area_id: str
    category: NeedCategory
    bucket: Optional[Bucket]
    value: Optional[int]
    coverage: Optional[CoverageLabel]
    method_version: Optional[str]
    source: Optional[str]
    created_at: datetime
    dedup_key: str


# ---------------------------------------------------------------------------
# Reporter communication (DOM-060..064)
# ---------------------------------------------------------------------------


class OutboundPurpose(StrEnum):
    conversation_reply = "conversation_reply"
    refresh_prompt = "refresh_prompt"
    area_broadcast = "area_broadcast"
    optout_confirmation = "optout_confirmation"


class GateBlockReason(StrEnum):
    opted_out = "opted_out"
    no_permission = "no_permission"
    outside_window_no_template = "outside_window_no_template"
    rate_limited = "rate_limited"


@dataclass(frozen=True)
class ReporterCommState:
    reporter_key: str
    opted_out_at: Optional[datetime] = None
    last_inbound_at: Optional[datetime] = None


@dataclass(frozen=True)
class OutboundIntent:
    reporter_key: str
    purpose: OutboundPurpose
    created_at: datetime
    template_id: Optional[str] = None
    need_id: Optional[str] = None
    broadcast_id: Optional[str] = None


@dataclass(frozen=True)
class SentMessage:
    reporter_key: str
    purpose: OutboundPurpose
    sent_at: datetime


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: Optional[GateBlockReason] = None


# ---------------------------------------------------------------------------
# Review (DOM-070..074)
# ---------------------------------------------------------------------------


class ReviewTaskKind(StrEnum):
    duplicate_candidate = "duplicate_candidate"
    conflicting_observation = "conflicting_observation"
    unresolved_location = "unresolved_location"
    flood = "flood"
    outlier_cell = "outlier_cell"
    urgent_flag = "urgent_flag"
    unparsed_text = "unparsed_text"


class ReviewTaskState(StrEnum):
    open = "open"
    resolved = "resolved"


class ComparisonKind(StrEnum):
    duplicate_candidate = "duplicate_candidate"
    conflict = "conflict"
    transition = "transition"


@dataclass(frozen=True)
class ComparisonResult:
    kind: ComparisonKind
    report_ids: tuple[str, ...]
    rule_version: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReviewTask:
    id: str
    kind: ReviewTaskKind
    report_ids: tuple[str, ...]
    state: ReviewTaskState
    created_at: datetime
    rule_version: Optional[str] = None
    reasons: tuple[str, ...] = ()
    area_id: Optional[str] = None


@dataclass(frozen=True)
class ReviewDisposition:
    task_id: str
    disposition: Disposition
    reviewer_id: str
    rationale: str
    decided_at: datetime
    review_after: Optional[datetime] = None
    primary_report_id: Optional[str] = None  # for duplicate merges
    corrected_area_id: Optional[str] = None  # for location_corrected


# ---------------------------------------------------------------------------
# Public dashboard (DOM-080/081)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicIndicatorCell:
    """CON-016: a separate model, never derived by subclassing IndicatorCell."""

    area_id: str
    level: AreaLevel
    subject: Subject
    bucket: Bucket
    bucket_end: datetime
    coverage: CoverageLabel
    need_count_band: Optional[str]
    status_mix_bands: Optional[Mapping[ServiceStatus, str]]
    freshness: Optional[datetime]


@dataclass(frozen=True)
class PublicActivity:
    provider_name: str
    type: ActivityType
    area_ids: frozenset[str]
    schedule_description: str
    public_location_id: Optional[str]

