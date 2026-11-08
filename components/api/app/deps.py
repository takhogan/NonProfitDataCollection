"""Auth dependency: resolve the JWT to a RequestContext.

The org ALWAYS comes from the authenticated user's membership (here, the fake
store; Step 2: the DB), NEVER from the request body. Data-protection settings are
loaded into the context so every handler can enforce them.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.context import RequestContext, resolve_data_protection
from app.errors import PermissionDenied
from app.fakestore import ORG_DATA_PROTECTION, ORG_PROFILE, USERS
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def _user_by_id(user_id: str) -> dict | None:
    for rec in USERS.values():
        if rec["user_id"] == user_id:
            return rec
    return None


def get_context(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> RequestContext:
    if creds is None or not creds.credentials:
        raise PermissionDenied("Missing bearer token")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise PermissionDenied("Invalid or expired token")
    rec = _user_by_id(user_id)
    if rec is None:
        raise PermissionDenied("Unknown user")

    dp = resolve_data_protection(ORG_DATA_PROTECTION.get(rec["org_id"], {}))
    org_name = ORG_PROFILE.get(rec["org_id"], {}).get("name", rec.get("org_name", ""))
    return RequestContext(
        org_id=rec["org_id"], actor_id=rec["user_id"],
        membership_id=f"mem-{rec['user_id']}", role=rec["role"],
        org_name=org_name, data_protection=dp,
    )
