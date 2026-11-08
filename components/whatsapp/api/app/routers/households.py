"""Households and assisted intake (first deliverable).

/v1/households/...            org derived from the session's active membership
/orgs/{org_id}/households/... legacy (deprecated); org checked against
                              memberships, 404 for non-members

Handlers are shared; only the org-context dependency differs.
"""
from __future__ import annotations

from collections.abc import Callable

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
from app.deps import get_org_context, get_v1_context
from app.domain import intake as intake_domain
from app.idempotency import idempotent

router = APIRouter(prefix="/v1/households", tags=["households"])
legacy_router = APIRouter(prefix="/orgs/{org_id}/households", tags=["legacy"], deprecated=True)


def _to_detail(household) -> HouseholdDetail:
    return HouseholdDetail(
        id=household.id,
        reference_code=household.reference_code,
        estimated_member_count=household.estimated_member_count,
        contacts=[PersonOut.model_validate(m.person) for m in household.members],
        cases=[CaseOut.model_validate(c) for c in household.cases],
    )


def _register(r: APIRouter, ctx_dep: Callable[..., RequestContext]) -> None:
    @r.post("", response_model=IntakeResult, status_code=201)
    def create_intake(
        body: AssistedIntakeRequest,
        request: Request,
        response: Response,
        ctx: RequestContext = Depends(ctx_dep),
        db: Session = Depends(get_db),
    ) -> IntakeResult:
        """Assisted intake: household + contacts + assessment + case in one txn.

        Supports Idempotency-Key for safe offline retries; reusing a key with a
        different body returns 409 `idempotency_conflict`.
        """
        with idempotent(request, response, ctx, db, endpoint="create_intake",
                        payload=body.model_dump(mode="json")) as replay:
            if replay.hit:
                return IntakeResult.model_validate(replay.body)
            result = intake_domain.create_assisted_intake(ctx, db, body)
            replay.store(201, result.model_dump(mode="json"))
            return result

    @r.get("/{household_id}", response_model=HouseholdDetail)
    def read_household(
        household_id: str,
        ctx: RequestContext = Depends(ctx_dep),
        db: Session = Depends(get_db),
    ) -> HouseholdDetail:
        return _to_detail(intake_domain.get_household(ctx, db, household_id))


_register(router, get_v1_context)
_register(legacy_router, get_org_context)
