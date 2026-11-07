"""Cases: list cases for the caller's organization (first deliverable)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.contracts.household import CaseSummary
from app.db import get_db
from app.deps import get_org_context
from app.domain import intake as intake_domain

router = APIRouter(prefix="/orgs/{org_id}/cases", tags=["cases"])


@router.get("", response_model=list[CaseSummary])
def list_cases(
    ctx: RequestContext = Depends(get_org_context),
    db: Session = Depends(get_db),
) -> list[CaseSummary]:
    cases = intake_domain.list_cases(ctx, db)
    return [CaseSummary.model_validate(c) for c in cases]
