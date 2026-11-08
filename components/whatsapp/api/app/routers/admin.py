"""Org-admin session management (API-012, part of API-090).

GET  /v1/admin/users/{user_id}/sessions         list a member's sessions
POST /v1/admin/users/{user_id}/revoke-sessions  end all of a member's sessions

The target must be a member (any status) of the admin's active organization,
otherwise 404. Sessions are re-read from the store on every request, so a
revocation takes effect on the target's next request.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.schemas import RevokeResult, SessionSummary
from app.auth.store import AuthStore, get_auth_store
from app.context import RequestContext
from app.db import get_db
from app.deps import ADMIN_ROLES, require_role
from app.errors import NotFound
from app.models.org import OrganizationMembership

log = logging.getLogger("app.audit")

router = APIRouter(prefix="/v1/admin/users", tags=["admin"])


def _require_member(db: Session, ctx: RequestContext, user_id: str) -> None:
    exists = db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == ctx.org_id,
        OrganizationMembership.user_id == user_id,
    ))
    if exists is None:
        raise NotFound("user not found")


@router.get("/{user_id}/sessions", response_model=list[SessionSummary])
def list_sessions(
    user_id: str,
    ctx: RequestContext = Depends(require_role(*ADMIN_ROLES)),
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    _require_member(db, ctx, user_id)
    return [SessionSummary.model_validate(s) for s in store.list_user_sessions(user_id)]


@router.post("/{user_id}/revoke-sessions", response_model=RevokeResult)
def revoke_sessions(
    user_id: str,
    ctx: RequestContext = Depends(require_role(*ADMIN_ROLES)),
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> RevokeResult:
    _require_member(db, ctx, user_id)
    n = store.revoke_user_sessions(user_id, sessions.now())
    # TODO(SEC-13): write to the append-only audit table once it exists.
    log.info("sessions_revoked", extra={"event": "sessions_revoked", "user_id": user_id,
                                        "org_id": ctx.org_id, "count": n})
    return RevokeResult(revoked=n)
