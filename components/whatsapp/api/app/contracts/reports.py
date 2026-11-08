"""Report submission contracts (CON-010, CON-011; semantics in DOM-010–DOM-031, DOM-060).

A report is what one resident (or a volunteer for them) says about services and
needs at one time. It carries no names. Location detail depends on the org's
privacy profile: ``meeting_point`` (protective) or ``address`` (standard). The
schema accepts either variant; the API rejects the variant the active profile
disallows with ``profile_violation`` (see ``admin.PrivacyProfileSettings``).
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .base import (
    AreaRef,
    ContractModel,
    LongText,
    NeedCategory,
    NonNegativeInt,
    OperationKey,
    Quantity,
    ServiceType,
    ShortText,
    TimePrecision,
    UtcInstant,
    Uuid,
    not_asked,
)
from .questionnaires import QuestionAnswer, QuestionnaireRef

Channel = Literal["whatsapp", "assisted_intake"]
ReportingRelationship = Literal["self", "household", "other_person", "area"]
ObservationStatus = Literal["available", "unavailable", "intermittent", "unknown"]
RemainingSupply = Literal["none", "little", "some", "unknown"]
StatedUrgency = Literal["urgent", "routine", "low", "unknown"]
AccessNote = Literal["cannot_leave_home", "no_containers", "mobility_limited", "other"]
PreferredTime = Literal["morning", "afternoon", "evening", "any", "unknown"]
NeedState = Literal["active", "stale", "resolved_by_reporter", "withdrawn", "expired"]
"""DOM-021: active → stale → resolved_by_reporter | withdrawn | expired."""
ReportState = Literal["draft", "confirmed", "superseded", "abandoned"]
PermissionPurpose = Literal[
    "notice_acknowledgement", "refresh_prompts", "area_broadcasts", "contact_list"
]

# Unit allowed for each need category's quantity. Liters, people and devices are never mixed.
NEED_QUANTITY_UNIT: dict[str, str] = {
    "water_drinking": "liters",
    "water_other": "liters",
    "charging": "devices",
}


class ReportedTime(ContractModel):
    """A time as the reporter gave it, with its precision (NFR-02, DOM-013).

    ``precision == "unknown"`` means the reporter does not know; ``at`` must then be
    omitted. Any other precision requires ``at``.
    """

    precision: TimePrecision
    at: UtcInstant = not_asked()

    @model_validator(mode="after")
    def _at_matches_precision(self) -> "ReportedTime":
        if self.precision == "unknown" and self.at is not None:
            raise ValueError("'at' must be omitted when precision is 'unknown'")
        if self.precision != "unknown" and self.at is None:
            raise ValueError("'at' is required unless precision is 'unknown'")
        return self


class Observation(ContractModel):
    """Status of one service as observed by the reporter (DOM-013)."""

    service: ServiceType
    status: ObservationStatus
    observed_at: ReportedTime
    outage_since: ReportedTime = not_asked(
        description="Onset of the outage, separate from observation time. Only for "
        "'unavailable' or 'intermittent'."
    )

    @model_validator(mode="after")
    def _onset_only_for_outage(self) -> "Observation":
        if self.outage_since is not None and self.status not in ("unavailable", "intermittent"):
            raise ValueError("'outage_since' applies only to unavailable or intermittent status")
        return self


class NeedDetail(ContractModel):
    """A household need recorded in a report (DOM-020). Never a dispatch request.

    Optional fields are "not asked" when omitted; ``"unknown"`` means asked and the
    reporter did not know ("No sé").
    """

    category: NeedCategory
    people_affected: NonNegativeInt | Literal["unknown"] = not_asked()
    quantity: Quantity | Literal["unknown"] = not_asked(
        description="liters for water categories, devices for charging"
    )
    remaining_supply: RemainingSupply = not_asked()
    stated_urgency: StatedUrgency
    access_notes: Annotated[list[AccessNote], Field(max_length=4)] = not_asked()
    preferred_times: Annotated[list[PreferredTime], Field(max_length=5)] = not_asked()

    @model_validator(mode="after")
    def _check(self) -> "NeedDetail":
        if isinstance(self.quantity, Quantity):
            expected = NEED_QUANTITY_UNIT[self.category]
            if self.quantity.unit != expected:
                raise ValueError(f"quantity unit for {self.category} must be '{expected}'")
        for name in ("access_notes", "preferred_times"):
            values = getattr(self, name)
            if values is not None and len(set(values)) != len(values):
                raise ValueError(f"{name} must not repeat values")
        if self.preferred_times and "unknown" in self.preferred_times and len(self.preferred_times) > 1:
            raise ValueError("'unknown' cannot be combined with other preferred times")
        return self


class PermissionDecision(ContractModel):
    """One separate, withdrawable permission (SEC-16, DOM-060)."""

    purpose: PermissionPurpose
    decision: Literal["granted", "declined"]
    notice_version: Annotated[int, Field(ge=1)]


# ---- Location detail (DOM-031) --------------------------------------------


class MeetingPointLocation(ContractModel):
    """Protective profile: a public meeting point in the reporter's sector, or none nearby."""

    kind: Literal["meeting_point"]
    meeting_point_id: Uuid | Literal["none_nearby"]


class GeoPoint(ContractModel):
    """WGS84 point. Only in the standard profile's address detail (SEC-03)."""

    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class AddressLocation(ContractModel):
    """Standard profile: address or landmark text, encrypted at rest, plus an optional point."""

    kind: Literal["address"]
    address_text: LongText
    landmark: ShortText = not_asked()
    point: GeoPoint = not_asked()


LocationDetail = Annotated[
    Union[MeetingPointLocation, AddressLocation], Field(discriminator="kind")
]
LocationKind = Literal["meeting_point", "address"]


# ---- Submission -----------------------------------------------------------


def _check_report_shape(report: "ReportSubmission | ReportDraft") -> None:
    if report.relationship == "area" and report.location is not None:
        raise ValueError("an area-only report carries no location detail")
    if report.observations is not None:
        services = [o.service for o in report.observations]
        if len(set(services)) != len(services):
            raise ValueError("at most one observation per service")
    if report.needs is not None:
        cats = [n.category for n in report.needs]
        if len(set(cats)) != len(cats):
            raise ValueError("at most one need per category")
    if report.permissions is not None:
        purposes = [p.purpose for p in report.permissions]
        if len(set(purposes)) != len(purposes):
            raise ValueError("at most one decision per permission purpose")


class ReportSubmission(ContractModel):
    """A confirmed report (DOM-010). Organization and actor come from context, never here.

    ``location`` is omitted for area-only reports and when the step was skipped.
    ``answers`` keeps the original questionnaire answers (CON-031).
    """

    channel: Channel
    relationship: ReportingRelationship
    area: AreaRef
    location: LocationDetail = not_asked()
    observations: Annotated[list[Observation], Field(max_length=2)]
    needs: Annotated[list[NeedDetail], Field(max_length=3)]
    permissions: Annotated[list[PermissionDecision], Field(max_length=4)]
    questionnaire: QuestionnaireRef
    answers: Annotated[list[QuestionAnswer], Field(max_length=100)] = not_asked()
    operation_key: OperationKey
    supersedes_report_id: Uuid = not_asked(description="Set for a correction (DOM-012).")

    @model_validator(mode="after")
    def _shape(self) -> "ReportSubmission":
        _check_report_shape(self)
        return self


class ReportDraft(ContractModel):
    """A report in progress (DOM-011): every field optional. Drafts never feed aggregates."""

    channel: Channel = not_asked()
    relationship: ReportingRelationship = not_asked()
    area: AreaRef = not_asked()
    location: LocationDetail = not_asked()
    observations: Annotated[list[Observation], Field(max_length=2)] = not_asked()
    needs: Annotated[list[NeedDetail], Field(max_length=3)] = not_asked()
    permissions: Annotated[list[PermissionDecision], Field(max_length=4)] = not_asked()
    questionnaire: QuestionnaireRef = not_asked()
    answers: Annotated[list[QuestionAnswer], Field(max_length=100)] = not_asked()
    operation_key: OperationKey = not_asked()
    supersedes_report_id: Uuid = not_asked()

    @model_validator(mode="after")
    def _shape(self) -> "ReportDraft":
        _check_report_shape(self)
        return self


class ReportAccepted(ContractModel):
    """Response to a submission. Replaying the same operation key returns the same body."""

    report_id: Uuid
    state: ReportState
    need_ids: list[Uuid]
    profile_version: Annotated[int, Field(ge=1)]
    received_at: UtcInstant


class NeedSummary(ContractModel):
    """Staff-facing need state, with no personal fields."""

    need_id: Uuid
    report_id: Uuid
    area: AreaRef
    category: NeedCategory
    state: NeedState
    stated_urgency: StatedUrgency
    created_at: UtcInstant
    last_confirmed_at: UtcInstant


__all__ = [
    "AccessNote",
    "AddressLocation",
    "Channel",
    "GeoPoint",
    "LocationDetail",
    "LocationKind",
    "MeetingPointLocation",
    "NEED_QUANTITY_UNIT",
    "NeedDetail",
    "NeedState",
    "NeedSummary",
    "Observation",
    "ObservationStatus",
    "PermissionDecision",
    "PermissionPurpose",
    "PreferredTime",
    "RemainingSupply",
    "ReportAccepted",
    "ReportDraft",
    "ReportState",
    "ReportSubmission",
    "ReportedTime",
    "ReportingRelationship",
    "StatedUrgency",
]
