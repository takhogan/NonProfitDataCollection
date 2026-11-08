"""Cases: list cases for the caller's organization (first deliverable).

/v1/cases (session org) and the deprecated /orgs/{org_id}/cases.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.contracts.household import CaseSummary
from app.db import get_db
from app.deps import get_org_context, get_v1_context
from app.domain import intake as intake_domain

router = APIRouter(prefix="/v1/cases", tags=["cases"])
legacy_router = APIRouter(prefix="/orgs/{org_id}/cases", tags=["legacy"], deprecated=True)


def _register(r: APIRouter, ctx_dep: Callable[..., RequestContext]) -> None:
    @r.get("", response_model=list[CaseSummary])
    def list_cases(
        ctx: RequestContext = Depends(ctx_dep),
        db: Session = Depends(get_db),
    ) -> list[CaseSummary]:
        return [CaseSummary.model_validate(c) for c in intake_domain.list_cases(ctx, db)]


_register(router, get_v1_context)
_register(legacy_router, get_org_context)
