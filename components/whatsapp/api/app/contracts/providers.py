"""Provider contracts (CON-014, CON-015; DOM-050–DOM-055, SEC-09).

Provider, activity and alert models carry no resident personal fields (CON-004).
The only model here with resident contact data is ``ContactListRow``, served to
vetted providers after consent, scope and profile checks (DOM-054).
"""
from __future__ import annotations

from datetime import date, time
from typing import Annotated, Literal, Union

from pydantic import BeforeValidator, Field, PlainSerializer, StringConstraints, WithJsonSchema, model_validator

from .base import (
    AreaRef,
    ContractModel,
    LocalTimezone,
    LongText,
    NeedCategory,
    NonNegativeInt,
    OperationKey,
    PhoneE164,
    ShortText,
    Slug,
    UtcInstant,
    Uuid,
    not_asked,
)
from .reports import PreferredTime, StatedUrgency

VettingStatus = Literal["unvetted", "vetted", "suspended"]
ActivityType = Literal["water_distribution_point", "water_delivery", "charging_point", "other"]
ActivityStatus = Literal["planned", "active", "paused", "ended"]
ActivityVisibility = Literal["tenant", "internal_only", "public"]
"""``tenant``: all providers in the org see details. ``internal_only``: counts toward
coverage, details hidden from other providers. ``public``: also on the public dashboard."""
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ApiKeyScope = Literal["aggregates:read", "activities:read", "activities:write", "contact_list:read"]
AlertChannel = Literal["email", "whatsapp"]  # D26 still open


def _parse_date(value: object) -> object:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("must be a YYYY-MM-DD date")


def _parse_time(value: object) -> object:
    if isinstance(value, time):
        return value
    if isinstance(value, str) and len(value) == 5:
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("must be an HH:MM local time")


LocalDate = Annotated[
    date,
    BeforeValidator(_parse_date),
    WithJsonSchema({"type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}),
]
LocalTime = Annotated[
    time,
    BeforeValidator(_parse_time),
    PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$"}),
]


class ProviderScope(ContractModel):
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=500)]
    categories: Annotated[list[NeedCategory], Field(min_length=1, max_length=3)]


class ProviderOrganization(ContractModel):
    """A provider inside the operating NGO's tenant. Admin and the provider's own view."""

    id: Uuid
    name: ShortText
    vetting_status: VettingStatus
    scope: ProviderScope
    responsible_contact_name: ShortText
    responsible_contact_email: Annotated[str, StringConstraints(pattern="^[^@\\s]+@[^@\\s]+$", max_length=254)]
    data_handling_statement_version: Annotated[int, Field(ge=1)] | None
    allow_name_in_broadcasts: bool
    vetted_at: UtcInstant | None
    created_at: UtcInstant


class VettingChange(ContractModel):
    """Org-admin command; a reason is mandatory (DOM-050)."""

    status: VettingStatus
    reason: LongText
    operation_key: OperationKey


# ---- Activities (DOM-051) -------------------------------------------------


class OneOffSchedule(ContractModel):
    kind: Literal["one_off"]
    date: LocalDate
    start_time: LocalTime
    end_time: LocalTime
    timezone: LocalTimezone


class RecurringSchedule(ContractModel):
    kind: Literal["recurring"]
    weekdays: Annotated[list[Weekday], Field(min_length=1, max_length=7)]
    start_time: LocalTime
    end_time: LocalTime
    timezone: LocalTimezone
    valid_from: LocalDate
    valid_until: LocalDate = not_asked()


Schedule = Annotated[Union[OneOffSchedule, RecurringSchedule], Field(discriminator="kind")]


class Capacity(ContractModel):
    value: Annotated[float, Field(gt=0, le=10_000_000)]
    unit: Literal["liters", "devices"]
    per: Literal["day"]


class MeetingPointSite(ContractModel):
    kind: Literal["meeting_point"]
    meeting_point_id: Uuid


class PublicSite(ContractModel):
    """A public place (never a household): name and description only, no coordinates."""

    kind: Literal["public_site"]
    area_id: Uuid
    name: ShortText
    description: LongText = not_asked()


PublicLocation = Annotated[Union[MeetingPointSite, PublicSite], Field(discriminator="kind")]

ACTIVITY_CAPACITY_UNIT = {"water_drinking": "liters", "water_other": "liters", "charging": "devices"}


def _check_activity(a: "ActivityInput | Activity") -> None:
    if a.capacity is not None and a.capacity.unit != ACTIVITY_CAPACITY_UNIT[a.category]:
        raise ValueError(f"capacity unit for {a.category} must be '{ACTIVITY_CAPACITY_UNIT[a.category]}'")
    if a.schedule.end_time <= a.schedule.start_time:
        raise ValueError("schedule end_time must be after start_time")


class ActivityInput(ContractModel):
    """Create or replace an activity. The provider organization comes from context."""

    type: ActivityType
    category: NeedCategory
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=100)]
    schedule: Schedule
    capacity: Capacity = not_asked()
    public_location: PublicLocation = not_asked()
    visibility: ActivityVisibility
    status: ActivityStatus
    operation_key: OperationKey

    @model_validator(mode="after")
    def _check(self) -> "ActivityInput":
        _check_activity(self)
        return self


class Activity(ContractModel):
    """An activity as other providers in the tenant see it (DOM-053)."""

    id: Uuid
    provider_organization_id: Uuid
    provider_name: ShortText
    type: ActivityType
    category: NeedCategory
    areas: Annotated[list[AreaRef], Field(min_length=1, max_length=100)]
    schedule: Schedule
    capacity: Capacity | None
    public_location: PublicLocation | None
    visibility: ActivityVisibility
    status: ActivityStatus
    unconfirmed: bool = Field(description="True when not confirmed for 7 days (DOM-051).")
    last_confirmed_at: UtcInstant
    created_at: UtcInstant

    @model_validator(mode="after")
    def _check(self) -> "Activity":
        _check_activity(self)
        return self


# ---- Alerts (DOM-055) -----------------------------------------------------


class NewUrgentNeedsTrigger(ContractModel):
    kind: Literal["new_urgent_needs"]


class ActiveNeedsAboveTrigger(ContractModel):
    kind: Literal["active_needs_above"]
    threshold: Annotated[int, Field(ge=1, le=100_000)]


class AreaUncoveredTrigger(ContractModel):
    kind: Literal["area_uncovered"]


class ExternalOutageTrigger(ContractModel):
    kind: Literal["external_outage_signal"]


AlertTrigger = Annotated[
    Union[NewUrgentNeedsTrigger, ActiveNeedsAboveTrigger, AreaUncoveredTrigger, ExternalOutageTrigger],
    Field(discriminator="kind"),
]


class AlertSubscriptionInput(ContractModel):
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=200)]
    category: NeedCategory
    trigger: AlertTrigger
    channel: AlertChannel
    operation_key: OperationKey


class AlertSubscription(ContractModel):
    id: Uuid
    user_id: Uuid
    provider_organization_id: Uuid
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=200)]
    category: NeedCategory
    trigger: AlertTrigger
    channel: AlertChannel
    active: bool
    dedup_window_hours: Annotated[int, Field(ge=1, le=168)]
    created_at: UtcInstant


class Alert(ContractModel):
    """An alert: aggregate fields only, already suppressed (DOM-055)."""

    id: Uuid
    subscription_id: Uuid
    trigger_kind: Literal["new_urgent_needs", "active_needs_above", "area_uncovered", "external_outage_signal"]
    area: AreaRef
    category: NeedCategory
    window_start: UtcInstant
    window_end: UtcInstant
    active_needs: NonNegativeInt | None = Field(description="Null when the cell is suppressed.")
    urgent_active_needs: NonNegativeInt | None
    coverage: Literal["covered", "uncovered", "unknown"]
    method_version: Slug
    created_at: UtcInstant


# ---- API keys (API-063) ---------------------------------------------------


class ApiKeyInput(ContractModel):
    name: ShortText
    scopes: Annotated[list[ApiKeyScope], Field(min_length=1, max_length=4)]
    expires_at: UtcInstant
    operation_key: OperationKey


class ApiKey(ContractModel):
    """API key metadata. Never contains the secret."""

    id: Uuid
    name: ShortText
    prefix: Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_]{4,16}$")]
    scopes: Annotated[list[ApiKeyScope], Field(min_length=1, max_length=4)]
    created_by_user_id: Uuid
    created_at: UtcInstant
    expires_at: UtcInstant
    last_used_at: UtcInstant | None
    revoked_at: UtcInstant | None


class ApiKeyCreated(ContractModel):
    """Returned once, at creation. The secret is never retrievable again."""

    key: ApiKey
    secret: Annotated[str, StringConstraints(min_length=32, max_length=128)]


# ---- Contact list (CON-015, DOM-054) --------------------------------------


class ContactMeetingPoint(ContractModel):
    meeting_point_id: Uuid
    name: ShortText


class _ContactRowCommon(ContractModel):
    row_id: Uuid
    need_id: Uuid
    category: NeedCategory
    urgency: StatedUrgency
    preferred_times: Annotated[list[PreferredTime], Field(max_length=5)]
    phone: PhoneE164
    consented_at: UtcInstant


class ProtectiveContactRow(_ContactRowCommon):
    """Protective profile: alias, sector and meeting point; no name or address."""

    profile: Literal["protective"]
    alias: Annotated[str, StringConstraints(pattern="^[A-Za-z0-9-]{3,32}$")]
    sector: AreaRef
    meeting_point: ContactMeetingPoint | Literal["none_nearby"]


class StandardContactRow(_ContactRowCommon):
    """Standard profile: name and address."""

    profile: Literal["standard"]
    name: ShortText
    address: LongText
    sector: AreaRef


ContactListRow = Annotated[
    Union[ProtectiveContactRow, StandardContactRow], Field(discriminator="profile")
]
