"""FastAPI dependencies: authenticate the user and derive org context.

CRITICAL: organization access is derived from the authenticated user's
memberships. The org_id comes from the URL path and is checked against the
caller's memberships; it is NEVER read from a request body. A non-member (or a
member of a different org) gets 404, which also avoids leaking that the org
exists.
"""
from __future__ import annotations

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.db import get_db
from app.errors import NotFound, PermissionDenied
from app.models.org import OrganizationMembership, User
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise PermissionDenied("Missing bearer token")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise PermissionDenied("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise PermissionDenied("Unknown user")
    return user


def get_org_context(
    org_id: str = Path(..., description="Organization the caller is acting within"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestContext:
    """Verify the user has an active membership in org_id and build the context."""
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None:
        # 404, not 403: do not reveal whether this org exists to a non-member.
        raise NotFound("Organization not found")
    return RequestContext(
        org_id=org_id,
        actor_id=user.id,
        membership_id=membership.id,
        role=membership.role,
    )
