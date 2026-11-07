"""Intake domain: assisted-intake creation and household/case retrieval.

Every function takes (ctx, db, ...) and scopes all reads and writes to
ctx.org_id. Domain code contains no HTTP concerns. Reads that miss within the
org raise NotFound (callers translate to 404) so cross-org access cannot
distinguish "exists elsewhere" from "does not exist".
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.context import RequestContext
from app.contracts.household import AssistedIntakeRequest, IntakeResult
from app.errors import Conflict, NotFound, ValidationError
from app.models.case import CaseRecord, Need
from app.models.household import Household, HouseholdMember, Person
from app.models.intake import Assessment, Observation

# Required unit per need category; prevents mixing liters with device sessions.
_CATEGORY_UNIT = {"water_delivery": "liters", "charging_access": "device_sessions"}


def _validate_needs(req: AssistedIntakeRequest) -> None:
    for need in req.needs:
        expected = _CATEGORY_UNIT[need.category]
        if need.unit is not None and need.unit != expected:
            raise ValidationError(
                f"need category {need.category} requires unit {expected}",
                details={"category": need.category, "unit": need.unit},
            )


def create_assisted_intake(
    ctx: RequestContext, db: Session, req: AssistedIntakeRequest
) -> IntakeResult:
    """Create household + contacts + assessment/observations + case/needs atomically."""
    _validate_needs(req)

    # Reference codes are unique per org; surface a clean conflict on reuse.
    existing = db.scalar(
        select(Household).where(
            Household.organization_id == ctx.org_id,
            Household.reference_code == req.reference_code,
        )
    )
    if existing is not None:
        raise Conflict(
            "household reference_code already exists",
            details={"reference_code": req.reference_code},
        )

    org = ctx.org_id

    household = Household(
        organization_id=org,
        reference_code=req.reference_code,
        estimated_member_count=req.estimated_member_count,
    )
    db.add(household)
    db.flush()  # assign household.id

    for person_in in req.contacts:
        person = Person(
            organization_id=org,
            preferred_name=person_in.preferred_name,
            preferred_language=person_in.preferred_language,
        )
        db.add(person)
        db.flush()
        db.add(
            HouseholdMember(
                organization_id=org,
                household_id=household.id,
                person_id=person.id,
                relationship_label=person_in.relationship_label,
            )
        )

    assessment = Assessment(
        organization_id=org,
        household_id=household.id,
        source_channel=req.source_channel,
        reporting_relationship=req.reporting_relationship,
        answers_json=req.answers,
    )
    db.add(assessment)
    db.flush()

    for obs in req.observations:
        db.add(
            Observation(
                organization_id=org,
                assessment_id=assessment.id,
                household_id=household.id,
                service_type=obs.service_type,
                status=obs.status,
                subject_scope=obs.subject_scope,
                observation_start_at=obs.observation_start_at,
                observation_end_at=obs.observation_end_at,
                time_precision=obs.time_precision,
                reported_timezone=obs.reported_timezone,
                source_kind=obs.source_kind,
            )
        )

    case = CaseRecord(
        organization_id=org,
        household_id=household.id,
        assigned_membership_id=ctx.membership_id,
        status="open",
    )
    db.add(case)
    db.flush()

    need_ids: list[str] = []
    for need_in in req.needs:
        need = Need(
            organization_id=org,
            case_id=case.id,
            assessment_id=assessment.id,
            category=need_in.category,
            requested_quantity=need_in.requested_quantity,
            unit=need_in.unit or _CATEGORY_UNIT[need_in.category],
            period_start=need_in.period_start,
            period_end=need_in.period_end,
            urgency=need_in.urgency,
            urgency_reasons=need_in.urgency_reasons,
            status="requested",
        )
        db.add(need)
        db.flush()
        need_ids.append(need.id)

    db.commit()

    return IntakeResult(
        household_id=household.id,
        case_id=case.id,
        assessment_id=assessment.id,
        need_ids=need_ids,
    )


def get_household(ctx: RequestContext, db: Session, household_id: str) -> Household:
    """Fetch a household with contacts and cases/needs, scoped to the org."""
    household = db.scalar(
        select(Household)
        .where(
            Household.id == household_id,
            Household.organization_id == ctx.org_id,
        )
        .options(
            selectinload(Household.members).selectinload(HouseholdMember.person),
            selectinload(Household.cases).selectinload(CaseRecord.needs),
        )
    )
    if household is None:
        raise NotFound("household not found")
    return household


def list_cases(ctx: RequestContext, db: Session) -> list[CaseRecord]:
    """List all cases for the caller's organization."""
    return list(
        db.scalars(
            select(CaseRecord)
            .where(CaseRecord.organization_id == ctx.org_id)
            .order_by(CaseRecord.opened_at.desc())
        )
    )
