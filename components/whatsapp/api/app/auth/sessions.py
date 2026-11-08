"""Server-side staff sessions (SEC-05) and their cookie.

- The cookie holds a 256-bit random token; the store keeps only its SHA-256.
- `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`. With Secure on and no cookie
  domain the name gets the `__Host-` prefix, which browsers bind to this host.
- Active sessions expire after 30 minutes idle or 12 hours absolute.
  Pre-auth sessions (between password and TOTP) expire after 5 minutes.
- Upgrading a pre-auth session to active rotates the token (no fixation).
- Every request re-reads the session from the store, so a revocation takes
  effect on the next request (SEC-06 asks for under 60 s).
- Each session has its own CSRF token, returned in JSON (never a cookie the
  web app must read, since the web app may live on a sibling host).
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.auth.store import AuthStore, StaffSession
from app.config import get_settings

ACTIVE = "active"
TOTP_ENROLL = "totp_enroll"
TOTP_VERIFY = "totp_verify"
PREAUTH_STAGES = (TOTP_ENROLL, TOTP_VERIFY)

# Avoid a store write on every request; idle accounting is to the minute.
_TOUCH_EVERY = timedelta(seconds=30)


def now() -> datetime:
    """Single clock for the auth package; tests monkeypatch this."""
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_name() -> str:
    s = get_settings()
    if s.session_cookie_secure and not s.session_cookie_domain:
        return "__Host-sid"
    return "sid"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_session(
    store: AuthStore,
    *,
    user_id: str,
    stage: str,
    auth_method: str,
    active_org_id: str | None = None,
) -> tuple[str, StaffSession]:
    s = get_settings()
    t = now()
    lifetime = (
        timedelta(hours=s.session_absolute_timeout_hours)
        if stage == ACTIVE
        else timedelta(minutes=s.preauth_timeout_minutes)
    )
    token = secrets.token_urlsafe(32)
    sess = StaffSession(
        id=secrets.token_urlsafe(12),
        token_hash=hash_token(token),
        user_id=user_id,
        stage=stage,
        auth_method=auth_method,
        csrf_token=secrets.token_urlsafe(32),
        created_at=t,
        last_seen_at=t,
        expires_at=t + lifetime,
        active_org_id=active_org_id,
    )
    store.add_session(sess)
    return token, sess


def resolve(store: AuthStore, token: str | None) -> StaffSession | None:
    """Return the live session for a cookie token, or None (and drop it if expired)."""
    if not token:
        return None
    sess = store.get_session_by_token_hash(hash_token(token))
    if sess is None or sess.revoked_at is not None:
        return None
    t = now()
    idle = timedelta(minutes=get_settings().session_idle_timeout_minutes)
    expired = t >= _aware(sess.expires_at)
    if sess.stage == ACTIVE and t - _aware(sess.last_seen_at) >= idle:
        expired = True
    if expired:
        store.delete_session(sess.id)
        return None
    if t - _aware(sess.last_seen_at) >= _TOUCH_EVERY:
        sess = replace(sess, last_seen_at=t)
        store.update_session(sess)
    return sess


def upgrade_to_active(
    store: AuthStore, preauth: StaffSession, active_org_id: str | None
) -> tuple[str, StaffSession]:
    """Replace a pre-auth session with a fresh active one (new token, new CSRF)."""
    store.delete_session(preauth.id)
    return create_session(
        store,
        user_id=preauth.user_id,
        stage=ACTIVE,
        auth_method=preauth.auth_method,
        active_org_id=active_org_id,
    )


def set_session_cookie(response: Response, token: str, sess: StaffSession) -> None:
    s = get_settings()
    max_age = max(0, int((_aware(sess.expires_at) - now()).total_seconds()))
    response.set_cookie(
        key=cookie_name(),
        value=token,
        max_age=max_age,
        path="/",
        domain=s.session_cookie_domain or None,
        secure=s.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=cookie_name(),
        path="/",
        domain=s.session_cookie_domain or None,
        secure=s.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
