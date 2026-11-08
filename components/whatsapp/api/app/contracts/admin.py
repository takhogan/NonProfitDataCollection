"""Review and admin contracts (CON-017; DOM-030–DOM-034, DOM-063, DOM-070–DOM-072).

``PrivacyProfileSettings`` enforces the platform minimums in the schema (k ≥ 3
everywhere) and the fixed rules of the ``protective`` profile. The API uses
``PrivacyProfileSettings.allows_location`` to reject a ``LocationDetail`` variant
the active profile disallows, with error code ``profile_violation``.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import (
    AreaRef,
    ContractModel,
    LocalTimezone,
    LongText,
    NonNegativeInt,
    OperationKey,
    PrivacyProfileName,
    ShortText,
    Slug,
    UtcInstant,
    Uuid,
    not_asked,
)
from .providers import LocalDate, LocalTime, Weekday
from .questionnaires import QuestionnaireRef

PLATFORM_MIN_K = 3

ContactListField = Literal["alias", "sector", "meeting_point", "name", "address", "phone"]
PROTECTIVE_CONTACT_FIELDS: frozenset[str] = frozenset({"alias", "sector", "meeting_point", "phone"})
STANDARD_CONTACT_FIELDS: frozenset[str] = frozenset({"name", "address", "phone"})

Role = Literal["org_admin", "coordinator", "reviewer", "intake_volunteer", "provider", "analyst"]


class PhoneRetention(ContractModel):
    mode: Literal["while_consented", "retention_policy"]
    days_after_last_activity: Annotated[int, Field(ge=1, le=730)]


class PublicDashboardSettings(ContractModel):
    enabled: bool
    level: Literal["parish", "sector"]
    k: Annotated[int, Field(ge=PLATFORM_MIN_K, le=1000)]
    delay_hours: Annotated[int, Field(ge=0, le=24 * 30)]


class PrivacyProfileSettings(ContractModel):
    """Each setting of a profile (DOM-030). Bounds in the schema are platform minimums."""

    names_allowed: bool
    location_mode: Literal["meeting_point", "address"]
    gps_allowed: bool
    reporter_phone_retention: PhoneRetention
    household_records_allowed: bool
    contact_list_enabled: bool
    contact_list_fields: Annotated[list[ContactListField], Field(max_length=6)]
    public_dashboard: PublicDashboardSettings
    aggregate_k: Annotated[int, Field(ge=PLATFORM_MIN_K, le=1000)]

    def allows_location(self, kind: str) -> bool:
        return kind == self.location_mode

    @model_validator(mode="after")
    def _consistent(self) -> "PrivacyProfileSettings":
        if self.gps_allowed and self.location_mode != "address":
            raise ValueError("gps_allowed requires location_mode 'address'")
        fields = set(self.contact_list_fields)
        if len(fields) != len(self.contact_list_fields):
            raise ValueError("contact_list_fields must not repeat")
        if self.contact_list_enabled and "phone" not in fields:
            raise ValueError("an enabled contact list includes phone")
        if self.public_dashboard.k < self.aggregate_k:
            raise ValueError("public k must be at least the aggregate k (SEC-17)")
        return self


class PlatformMinimums(ContractModel):
    """The floor each setting may not go below, for display beside the setting."""

    aggregate_k: Literal[3]
    public_k: Literal[3]
    protective_public_k: Literal[10]
    protective_public_delay_hours: Literal[24]


PLATFORM_MINIMUMS = PlatformMinimums(
    aggregate_k=3, public_k=3, protective_public_k=10, protective_public_delay_hours=24
)


class PrivacyProfile(ContractModel):
    """A versioned org policy. ``protective`` fixes the settings that make it protective."""

    id: Uuid
    version: Annotated[int, Field(ge=1)]
    name: PrivacyProfileName
    notice_version: Annotated[int, Field(ge=1)]
    settings: PrivacyProfileSettings
    platform_minimums: PlatformMinimums
    status: Literal["draft", "active", "superseded"]
    activated_at: UtcInstant | None

    @model_validator(mode="after")
    def _profile_rules(self) -> "PrivacyProfile":
        s = self.settings
        if self.name == "protective":
            if s.names_allowed or s.gps_allowed or s.household_records_allowed:
                raise ValueError("protective profile allows no names, GPS or household records")
            if s.location_mode != "meeting_point":
                raise ValueError("protective profile uses meeting points")
            if s.reporter_phone_retention.mode != "while_consented":
                raise ValueError("protective profile keeps phones only while consented")
            if not set(s.contact_list_fields) <= PROTECTIVE_CONTACT_FIELDS:
                raise ValueError("protective contact list fields: alias, sector, meeting_point, phone")
            pd = s.public_dashboard
            if pd.level != "parish" or pd.k < 10 or pd.delay_hours < 24:
                raise ValueError("protective public dashboard: parish level, k ≥ 10, delay ≥ 24h")
        else:
            if not set(s.contact_list_fields) <= STANDARD_CONTACT_FIELDS | {"sector"}:
                raise ValueError("standard contact list fields: name, address, sector, phone")
        return self


class PolicyVersion(ContractModel):
    id: Uuid
    kind: Literal["privacy_profile", "privacy_notice", "data_handling_statement", "retention"]
    version: Annotated[int, Field(ge=1)]
    content_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    effective_from: UtcInstant
    created_by_user_id: Uuid
    created_at: UtcInstant


class Membership(ContractModel):
    id: Uuid
    user_id: Uuid
    roles: Annotated[list[Role], Field(min_length=1, max_length=6)]
    status: Literal["active", "suspended", "revoked"]
    provider_organization_id: Uuid | None = Field(
        description="Set exactly when roles include 'provider'."
    )
    created_at: UtcInstant

    @model_validator(mode="after")
    def _provider(self) -> "Membership":
        if ("provider" in self.roles) != (self.provider_organization_id is not None):
            raise ValueError("provider_organization_id is set exactly for provider members")
        return self


class StaffedHours(ContractModel):
    weekdays: Annotated[list[Weekday], Field(min_length=1, max_length=7)]
    start_time: LocalTime
    end_time: LocalTime


class CampaignConfig(ContractModel):
    id: Uuid
    name: ShortText
    display_identity: ShortText = Field(description="Resident-facing name, e.g. 'Metron Reporter'.")
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=500)]
    questionnaire: QuestionnaireRef
    staffed_hours: Annotated[list[StaffedHours], Field(max_length=14)]
    timezone: LocalTimezone
    urgent_referral_key: Slug | None = Field(description="Urgent referral content (D15); null until set.")
    starts_on: LocalDate
    ends_on: LocalDate | None
    status: Literal["draft", "active", "paused", "ended"]


MeetingPointType = Literal["plaza", "church", "school", "bodega", "community_center", "other"]


class MeetingPointInput(ContractModel):
    sector_id: Uuid
    name: ShortText
    type: MeetingPointType
    description: Annotated[str, Field(min_length=1, max_length=500)]
    operation_key: OperationKey


class MeetingPoint(ContractModel):
    """A public place in a sector (DOM-034). Holds no personal data."""

    id: Uuid
    sector: AreaRef
    name: ShortText
    type: MeetingPointType
    description: Annotated[str, Field(min_length=1, max_length=500)]
    active: bool
    created_at: UtcInstant

    @model_validator(mode="after")
    def _sector(self) -> "MeetingPoint":
        if self.sector.level != "sector":
            raise ValueError("meeting points belong to a sector")
        return self


BroadcastStatus = Literal["draft", "approved", "sending", "sent", "cancelled"]


class BroadcastInput(ContractModel):
    template_key: Slug
    activity_id: Uuid
    include_provider_name: bool
    operation_key: OperationKey


class Broadcast(ContractModel):
    """An area-information broadcast (DOM-063). Recipients are counted, never listed."""

    id: Uuid
    template_key: Slug
    activity_id: Uuid
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=100)]
    include_provider_name: bool
    status: BroadcastStatus
    recipient_count: NonNegativeInt | None = Field(description="Null until the audience is resolved.")
    created_by_user_id: Uuid
    approved_by_user_id: Uuid | None
    approved_at: UtcInstant | None
    created_at: UtcInstant


ReviewTaskKind = Literal[
    "duplicate_candidate",
    "conflicting_observations",
    "unresolved_location",
    "flood",
    "outlier_cell",
    "urgent_flag",
    "unparsed_text",
    "external_evidence",
]
ReviewOutcome = Literal["valid", "duplicate", "spam", "location_corrected", "unresolved"]


class ReviewTask(ContractModel):
    """A data-quality task (DOM-070). References reports by ID only."""

    id: Uuid
    kind: ReviewTaskKind
    status: Literal["open", "in_progress", "resolved", "deferred"]
    area: AreaRef | None
    report_ids: Annotated[list[Uuid], Field(max_length=200)]
    rule_version: Slug
    reasons: Annotated[list[Slug], Field(min_length=1, max_length=20)]
    created_at: UtcInstant
    review_after: UtcInstant | None


class ReviewDispositionInput(ContractModel):
    outcome: ReviewOutcome
    rationale: LongText
    review_after: UtcInstant = not_asked()
    duplicate_of_report_id: Uuid = not_asked()
    spam_reason: Literal["bot", "coordinated", "test", "abusive", "other"] = not_asked()
    corrected_area: AreaRef = not_asked()
    operation_key: OperationKey

    @model_validator(mode="after")
    def _outcome_fields(self) -> "ReviewDispositionInput":
        _check_outcome(self.outcome, self.duplicate_of_report_id, self.spam_reason, self.corrected_area)
        return self


class ReviewDisposition(ContractModel):
    """A recorded disposition (DOM-072). Only duplicate or spam removes a report."""

    id: Uuid
    task_id: Uuid
    outcome: ReviewOutcome
    rationale: LongText
    reviewer_user_id: Uuid
    review_after: UtcInstant | None
    duplicate_of_report_id: Uuid | None
    spam_reason: Literal["bot", "coordinated", "test", "abusive", "other"] | None
    corrected_area: AreaRef | None
    decided_at: UtcInstant

    @model_validator(mode="after")
    def _outcome_fields(self) -> "ReviewDisposition":
        _check_outcome(self.outcome, self.duplicate_of_report_id, self.spam_reason, self.corrected_area)
        return self


def _check_outcome(outcome: str, duplicate_of: object, spam_reason: object, area: object) -> None:
    if (outcome == "duplicate") != (duplicate_of is not None):
        raise ValueError("duplicate_of_report_id is set exactly for 'duplicate'")
    if (outcome == "spam") != (spam_reason is not None):
        raise ValueError("spam_reason is set exactly for 'spam'")
    if (outcome == "location_corrected") != (area is not None):
        raise ValueError("corrected_area is set exactly for 'location_corrected'")


