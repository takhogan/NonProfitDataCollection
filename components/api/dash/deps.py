"""Auth dependency: resolve the JWT to a RequestContext from the shared DB.

The org ALWAYS comes from the authenticated user's membership in the database,
never from the request body. Data-protection settings are loaded (from the org's
active privacy profile when present, else the stored dashboard settings) so every
handler can enforce them.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from dash.context import RequestContext, resolve_data_protection
from dash.errors import PermissionDenied
from dash.read_models import primary_membership, user_by_id
from dash.security import decode_access_token
from dash.shared_db import session_scope
from dash import settings_store

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Session:
    yield from session_scope()


def get_context(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> RequestContext:
    if creds is None or not creds.credentials:
        raise PermissionDenied("Missing bearer token")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise PermissionDenied("Invalid or expired token")

    user = user_by_id(db, user_id)
    if user is None:
        raise PermissionDenied("Unknown user")
    pm = primary_membership(db, user_id)
    if pm is None:
        raise PermissionDenied("User has no active organization membership")
    membership, org = pm

    # Data-protection: dashboard-managed settings are durable (policy_version via
    # settings_store). The intake-side privacy_profile_version governs intake
    # enforcement; this governs dashboard responses. Default to standard.
    stored = settings_store.get_setting(db, org.id, "data_protection", {"preset": "standard"})
    dp = resolve_data_protection(stored)
    return RequestContext(
        org_id=org.id, actor_id=user.id, membership_id=membership.id,
        role=membership.role, org_name=org.name, data_protection=dp,
    )
