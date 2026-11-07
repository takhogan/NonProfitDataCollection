"""Households and assisted intake (first deliverable).

All routes are org-scoped: /orgs/{org_id}/households/... The org context is
derived from the authenticated membership via get_org_context.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.contracts.household import (
    AssistedIntakeRequest,
    CaseOut,
    HouseholdDetail,
    IntakeResult,
    PersonOut,
)
from app.db import get_db
from app.deps import get_org_context
from app.domain import intake as intake_domain
from app.idempotency import idempotent

router = APIRouter(prefix="/orgs/{org_id}/households", tags=["households"])


def _to_detail(household) -> HouseholdDetail:
    return HouseholdDetail(
        id=household.id,
        reference_code=household.reference_code,
        estimated_member_count=household.estimated_member_count,
        contacts=[PersonOut.model_validate(m.person) for m in household.members],
        cases=[CaseOut.model_validate(c) for c in household.cases],
    )


@router.post("", response_model=IntakeResult, status_code=201)
def create_intake(
    body: AssistedIntakeRequest,
    request: Request,
    response: Response,
    ctx: RequestContext = Depends(get_org_context),
    db: Session = Depends(get_db),
) -> IntakeResult:
    """Assisted intake: household + contacts + assessment + case in one txn.

    Supports Idempotency-Key for safe offline retries.
    """
    with idempotent(request, response, ctx, db, endpoint="create_intake") as replay:
        if replay.hit:
            return IntakeResult.model_validate(replay.body)
        result = intake_domain.create_assisted_intake(ctx, db, body)
        replay.store(201, result.model_dump())
        return result


@router.get("/{household_id}", response_model=HouseholdDetail)
def read_household(
    household_id: str,
    ctx: RequestContext = Depends(get_org_context),
    db: Session = Depends(get_db),
) -> HouseholdDetail:
    household = intake_domain.get_household(ctx, db, household_id)
    return _to_detail(household)
