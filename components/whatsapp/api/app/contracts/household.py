"""DEPRECATED: household/case contracts from the first intake slice.

Superseded by the report-centric v1 contracts (``reports``, ``aggregation``,
``providers``). Kept only until the api session migrates its routers; do not use
in new code. Note the old need categories (``water_delivery``, ``charging_access``)
and units (``device_sessions``) are not valid in v1.

Assisted-intake request and household detail response contracts.

These are the API boundary types; they do not expose raw DB rows. Units stay
explicit (liters vs device sessions); unknown stays unknown rather than defaulting
to zero/false.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ServiceType = Literal["electricity", "piped_water"]
ObservationStatus = Literal["available", "unavailable", "intermittent", "unknown"]
SourceChannel = Literal["whatsapp", "phone", "volunteer_assisted"]
ReportingRelationship = Literal["self", "household", "other_person", "area"]
NeedCategory = Literal["water_delivery", "charging_access"]
Urgency = Literal["low", "routine", "urgent", "unknown"]


class ObservationIn(BaseModel):
    service_type: ServiceType
    status: ObservationStatus = "unknown"
    subject_scope: Literal["household", "area"] = "household"
    observation_start_at: datetime | None = None
    observation_end_at: datetime | None = None
    time_precision: str = "unknown"
    reported_timezone: str = "America/Caracas"
    source_kind: str = "firsthand"


class NeedIn(BaseModel):
    category: NeedCategory
    # liters for water_delivery, device_sessions for charging_access; may be
    # unknown (None) per the spec — do not coerce to 0.
    requested_quantity: float | None = Field(default=None, ge=0)
    unit: Literal["liters", "device_sessions"] | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    urgency: Urgency = "unknown"
    urgency_reasons: list[str] = Field(default_factory=list)


class PersonIn(BaseModel):
    preferred_name: str | None = None
    preferred_language: str | None = None
    relationship_label: str | None = None


class AssistedIntakeRequest(BaseModel):
    """Create a household, its contacts, and an initial assessment/case in one txn.

    Note: no organization_id here on purpose. Org is derived from the URL + the
    caller's membership, never from the body.
    """

    reference_code: str
    estimated_member_count: int | None = Field(default=None, ge=0)
    contacts: list[PersonIn] = Field(default_factory=list)
    source_channel: SourceChannel = "volunteer_assisted"
    reporting_relationship: ReportingRelationship = "household"
    answers: dict = Field(default_factory=dict)
    observations: list[ObservationIn] = Field(default_factory=list)
    needs: list[NeedIn] = Field(default_factory=list)


# ---- Responses -------------------------------------------------------------

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    preferred_name: str | None = None
    preferred_language: str | None = None


class NeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    requested_quantity: float | None = None
    unit: str | None = None
    urgency: str
    status: str


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    opened_at: datetime
    needs: list[NeedOut] = Field(default_factory=list)


class HouseholdDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reference_code: str
    estimated_member_count: int | None = None
    contacts: list[PersonOut] = Field(default_factory=list)
    cases: list[CaseOut] = Field(default_factory=list)


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    household_id: str
    status: str
    opened_at: datetime


class IntakeResult(BaseModel):
    household_id: str
    case_id: str
    assessment_id: str
    need_ids: list[str]
