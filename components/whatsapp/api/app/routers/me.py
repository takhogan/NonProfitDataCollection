"""Current user context (API-011) and self-service revocation (API-012).

GET  /v1/me                      memberships, active org and role, session info,
                                 CSRF token
POST /v1/me/active-organization  switch the session's org among own memberships
POST /v1/me/revoke-all           end every session of the caller (SEC-06)
GET  /me                         legacy (deprecated) shape, kept for the
                                 deployed service and existing clients
"""
from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.schemas import (
    MembershipV1,
    MeV1,
    RevokeResult,
    SessionInfo,
    SetActiveOrganization,
)
from app.auth.store import AuthStore, get_auth_store
from app.config import get_settings
from app.contracts.common import MembershipOut, MeResponse
from app.db import get_db
from app.deps import Principal, active_memberships, get_current_user, get_principal
from app.errors import NotFound
from app.models.org import Organization, OrganizationMembership, User

router = APIRouter(prefix="/v1/me", tags=["me"])
legacy_router = APIRouter(prefix="/me", tags=["legacy"], deprecated=True)


def _me_v1(principal: Principal, db: Session) -> MeV1:
    user = principal.user
    ms = active_memberships(db, user.id)
    names = dict(db.execute(
        select(Organization.id, Organization.name)
        .where(Organization.id.in_([m.organization_id for m in ms]))
    ).all()) if ms else {}
    sess = principal.session
    if sess is not None:
        active_org = sess.active_org_id
    else:
        active_org = ms[0].organization_id if ms else None
    active = next((m for m in ms if m.organization_id == active_org), None)
    return MeV1(
        id=user.id,
        email=user.auth_subject,
        display_name=user.display_name,
        active_organization_id=active.organization_id if active else None,
        role=active.role if active else None,
        memberships=[
            MembershipV1(id=m.id, organization_id=m.organization_id,
                         organization_name=names.get(m.organization_id, ""),
                         role=m.role, status=m.status)
            for m in ms
        ],
        auth_method=principal.auth_method,
        session=SessionInfo(
            auth_method=sess.auth_method, created_at=sess.created_at,
            expires_at=sess.expires_at,
            idle_timeout_seconds=get_settings().session_idle_timeout_minutes * 60,
        ) if sess else None,
        csrf_token=sess.csrf_token if sess else None,
    )


@router.get("", response_model=MeV1)
def read_me_v1(
    principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> MeV1:
    return _me_v1(principal, db)


@router.post("/active-organization", response_model=MeV1)
def set_active_organization(
    body: SetActiveOrganization,
    principal: Principal = Depends(get_principal),
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> MeV1:
    member = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == body.organization_id,
        OrganizationMembership.user_id == principal.user.id,
        OrganizationMembership.status == "active",
    ))
    if member is None or principal.session is None:
        raise NotFound("Organization not found")
    principal.session = replace(principal.session, active_org_id=member.organization_id)
    store.update_session(principal.session)
    return _me_v1(principal, db)


@router.post("/revoke-all", response_model=RevokeResult)
def revoke_all(
    response: Response,
    principal: Principal = Depends(get_principal),
    store: AuthStore = Depends(get_auth_store),
) -> RevokeResult:
    n = store.revoke_user_sessions(principal.user.id, sessions.now())
    sessions.clear_session_cookie(response)
    return RevokeResult(revoked=n)


@legacy_router.get("", response_model=MeResponse)
def read_me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        auth_subject=user.auth_subject,
        display_name=user.display_name,
        memberships=[MembershipOut.model_validate(m) for m in user.memberships],
    )
