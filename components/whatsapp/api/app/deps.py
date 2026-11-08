"""FastAPI dependencies: authenticate the caller and derive org context.

Authentication (in order):
1. The server-side session cookie (production path, API-010). Unsafe methods
   also need the session's CSRF token in `X-CSRF-Token` and, when the browser
   sends one, an `Origin` equal to the configured web origin (API-013).
2. A JWT bearer token, only outside production (API-014 dev fixture).

CRITICAL: organization access is derived from the authenticated user's
memberships, never from a request body.
- `/v1` routes use the session's active organization, re-checked against an
  active membership on every request (so removing a membership takes effect
  immediately).
- Legacy `/orgs/{org_id}` routes check the path org against memberships.
A non-member gets 404, which avoids leaking that an org exists.
"""
from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Path, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import sessions
from app.auth.store import AuthStore, StaffSession, get_auth_store
from app.config import get_settings
from app.context import RequestContext
from app.db import get_db
from app.errors import NotFound, PermissionDenied, Unauthenticated
from app.models.org import OrganizationMembership, User
from app.security import decode_access_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-CSRF-Token"
# org_admin is the requirements' name; administrator is the current model's.
ADMIN_ROLES = ("org_admin", "administrator")


@dataclass
class Principal:
    user: User
    auth_method: str                 # "session" | "dev_bearer"
    session: StaffSession | None = None


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.auth_subject) == email.strip().lower()))


def active_memberships(db: Session, user_id: str) -> list[OrganizationMembership]:
    return list(db.scalars(
        select(OrganizationMembership)
        .where(OrganizationMembership.user_id == user_id,
               OrganizationMembership.status == "active")
        .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
    ))


def check_origin(request: Request) -> None:
    """Reject cross-origin browser mutations (defense in depth beside CSRF)."""
    origin = request.headers.get("origin")
    web_origin = get_settings().web_origin.rstrip("/")
    if origin and web_origin and origin.rstrip("/") != web_origin:
        raise PermissionDenied("bad origin", message_key="errors.csrf")


def check_csrf(request: Request, sess: StaffSession) -> None:
    if request.method in SAFE_METHODS:
        return
    check_origin(request)
    sent = request.headers.get(CSRF_HEADER, "")
    if not sent or not hmac.compare_digest(sent, sess.csrf_token):
        raise PermissionDenied("missing or bad CSRF token", message_key="errors.csrf")


def _session_from_cookie(request: Request, store: AuthStore) -> StaffSession | None:
    return sessions.resolve(store, request.cookies.get(sessions.cookie_name()))


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def get_principal(
    request: Request,
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> Principal:
    sess = _session_from_cookie(request, store)
    if sess is not None and sess.stage == sessions.ACTIVE:
        user = db.get(User, sess.user_id)
        if user is None:
            store.delete_session(sess.id)
            raise Unauthenticated("unknown user")
        check_csrf(request, sess)
        request.state.user_id = user.id
        request.state.auth_method = "session"
        return Principal(user=user, auth_method="session", session=sess)

    token = _bearer_token(request)
    if token is not None and not get_settings().is_production:
        user_id = decode_access_token(token)
        user = db.get(User, user_id) if user_id else None
        if user is not None:
            request.state.user_id = user.id
            request.state.auth_method = "dev_bearer"
            return Principal(user=user, auth_method="dev_bearer")

    raise Unauthenticated("not signed in")


# Kept for callers that only need the user.
def get_current_user(principal: Principal = Depends(get_principal)) -> User:
    return principal.user


def get_preauth_session(
    request: Request, store: AuthStore = Depends(get_auth_store)
) -> StaffSession:
    """The half-signed-in session between password and TOTP."""
    sess = _session_from_cookie(request, store)
    if sess is None or sess.stage not in sessions.PREAUTH_STAGES:
        raise Unauthenticated("no pending sign-in")
    check_csrf(request, sess)
    return sess


def _membership(db: Session, org_id: str, user_id: str) -> OrganizationMembership | None:
    return db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )


def _ctx(m: OrganizationMembership) -> RequestContext:
    return RequestContext(
        org_id=m.organization_id, actor_id=m.user_id, membership_id=m.id, role=m.role
    )


def get_v1_context(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> RequestContext:
    """Org context for /v1 routes, derived from the session's active membership."""
    if principal.session is not None:
        org_id = principal.session.active_org_id
    else:
        # Dev bearer only: optional X-Org-Id picks among the caller's own
        # memberships; otherwise the first active one.
        org_id = request.headers.get("x-org-id")
        if not org_id:
            ms = active_memberships(db, principal.user.id)
            org_id = ms[0].organization_id if ms else None
    m = _membership(db, org_id, principal.user.id) if org_id else None
    if m is None:
        raise PermissionDenied(
            "no active organization", message_key="errors.no_active_organization"
        )
    request.state.org_id = m.organization_id
    return _ctx(m)


def get_org_context(
    org_id: str = Path(..., description="Organization the caller is acting within"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> RequestContext:
    """Legacy /orgs/{org_id} routes: verify membership in the path org."""
    m = _membership(db, org_id, principal.user.id)
    if m is None:
        # 404, not 403: do not reveal whether this org exists to a non-member.
        raise NotFound("Organization not found")
    return _ctx(m)


def require_role(*roles: str) -> Callable[..., RequestContext]:
    """Dependency factory: the caller's role in the active org must be one of roles."""
    allowed = set(roles)

    def _dep(ctx: RequestContext = Depends(get_v1_context)) -> RequestContext:
        if ctx.role not in allowed:
            raise PermissionDenied("role not allowed")
        return ctx

    return _dep
