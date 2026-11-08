"""Staff sign-in (API-010) and the development-only bearer login (API-014).

/v1/auth/password/login     email + password -> pre-auth session cookie
/v1/auth/totp/enroll        first sign-in: get a TOTP secret (pre-auth only)
/v1/auth/totp/verify        TOTP code -> rotated, active session cookie
/v1/auth/oidc/google/start  redirect to Google (code + PKCE)
/v1/auth/oidc/google/callback  verify, create session, redirect to web app
/v1/auth/logout             end the current session

/auth/login                 DEV ONLY: email + password -> JWT. Not mounted in
                            production, and refuses there even if mounted.

All sign-in failures return the same `unauthenticated` error.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import credentials, sessions
from app.auth.oidc import OidcError, OidcProvider, get_oidc_provider
from app.auth.ratelimit import limit_signin
from app.auth.schemas import (
    PasswordLoginRequest,
    SignInStep,
    TotpCodeRequest,
    TotpEnrollment,
)
from app.auth.store import (
    AuthStore,
    OidcFlow,
    PasswordCredential,
    StaffSession,
    get_auth_store,
)
from app.config import get_settings
from app.contracts.common import LoginRequest, TokenResponse
from app.db import get_db
from app.deps import (
    Principal,
    active_memberships,
    check_origin,
    find_user_by_email,
    get_preauth_session,
    get_principal,
)
from app.errors import NotFound, Unauthenticated
from app.models.org import User
from app.security import create_access_token, verify_password

log = logging.getLogger("app.auth")

router = APIRouter(prefix="/v1/auth", tags=["auth"])
dev_router = APIRouter(prefix="/auth", tags=["auth (dev only)"])

_GENERIC = "invalid credentials"


def _fail() -> Unauthenticated:
    return Unauthenticated(_GENERIC, message_key="errors.sign_in_failed")


# --- Development-only bearer login -------------------------------------------

@dev_router.post("/login", response_model=TokenResponse, deprecated=True,
                 dependencies=[Depends(limit_signin)])
def dev_login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if get_settings().is_production:
        raise NotFound("not available")
    user = find_user_by_email(db, body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise _fail()
    return TokenResponse(access_token=create_access_token(user.id))


# --- Password + TOTP -----------------------------------------------------------

@router.post("/password/login", response_model=SignInStep,
             dependencies=[Depends(limit_signin)])
def password_login(
    body: PasswordLoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> SignInStep:
    check_origin(request)
    user = find_user_by_email(db, body.email)
    if (user is not None and not get_settings().is_production
            and store.get_password(user.id) is None
            and verify_password(body.password, user.password_hash)):
        # Development only: seeded users have just the legacy bcrypt hash and
        # the auth store is in memory, so adopt the seed password as an Argon2
        # credential. TOTP enrollment is still required.
        store.put_password(PasswordCredential(
            user_id=user.id, password_hash=credentials.hash_password(body.password)))
    ok = credentials.check_password(store, user.id if user else None, body.password)
    if not ok or user is None or not active_memberships(db, user.id):
        log.info("sign_in_failed", extra={"event": "password", "reason": "generic"})
        raise _fail()
    # Drop whatever session this browser had; a sign-in always starts fresh.
    prior = request.cookies.get(sessions.cookie_name())
    if prior:
        old = store.get_session_by_token_hash(sessions.hash_token(prior))
        if old is not None:
            store.delete_session(old.id)
    totp = store.get_totp(user.id)
    stage = sessions.TOTP_VERIFY if totp and totp.confirmed_at else sessions.TOTP_ENROLL
    token, sess = sessions.create_session(
        store, user_id=user.id, stage=stage, auth_method="password_totp"
    )
    sessions.set_session_cookie(response, token, sess)
    return SignInStep(stage=stage, csrf_token=sess.csrf_token)


@router.post("/totp/enroll", response_model=TotpEnrollment)
def totp_enroll(
    sess: StaffSession = Depends(get_preauth_session),
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> TotpEnrollment:
    if sess.stage != sessions.TOTP_ENROLL:
        raise _fail()
    user = db.get(User, sess.user_id)
    if user is None:
        raise _fail()
    secret = credentials.start_totp_enrollment(store, user.id)
    return TotpEnrollment(
        secret=secret, otpauth_uri=credentials.provisioning_uri(secret, user.auth_subject)
    )


@router.post("/totp/verify", response_model=SignInStep,
             dependencies=[Depends(limit_signin)])
def totp_verify(
    body: TotpCodeRequest,
    response: Response,
    sess: StaffSession = Depends(get_preauth_session),
    store: AuthStore = Depends(get_auth_store),
    db: Session = Depends(get_db),
) -> SignInStep:
    enrolling = sess.stage == sessions.TOTP_ENROLL
    if credentials.is_locked(store, sess.user_id) or not credentials.verify_totp(
        store, sess.user_id, body.code, enrolling=enrolling
    ):
        credentials.register_failure(store, sess.user_id)
        if credentials.is_locked(store, sess.user_id):
            store.delete_session(sess.id)  # start over after the lockout
        log.info("sign_in_failed", extra={"event": "totp", "reason": "generic"})
        raise _fail()
    ms = active_memberships(db, sess.user_id)
    if not ms:
        store.delete_session(sess.id)
        raise _fail()
    credentials.clear_failures(store, sess.user_id)
    token, active = sessions.upgrade_to_active(store, sess, ms[0].organization_id)
    sessions.set_session_cookie(response, token, active)
    log.info("signed_in", extra={"user_id": sess.user_id, "auth_method": "password_totp"})
    return SignInStep(stage="active", csrf_token=active.csrf_token)


@router.post("/logout", status_code=204)
def logout(
    principal: Principal = Depends(get_principal),
    store: AuthStore = Depends(get_auth_store),
) -> Response:
    if principal.session is not None:
        store.delete_session(principal.session.id)
    resp = Response(status_code=204)
    sessions.clear_session_cookie(resp)
    return resp


# --- Google OIDC -----------------------------------------------------------------

def _flow_cookie_name() -> str:
    s = get_settings()
    return "__Host-oidc" if s.session_cookie_secure and not s.session_cookie_domain else "oidc"


def safe_next_path(next_path: str | None) -> str:
    """Only same-site relative paths: no scheme, no host, no backslashes."""
    p = next_path or "/"
    if (not p.startswith("/") or p.startswith("//") or "\\" in p or "://" in p
            or len(p) > 512 or any(ord(c) < 0x20 for c in p)):
        return "/"
    return p


def _web_url(path: str) -> str:
    return (get_settings().web_origin.rstrip("/") or "") + path


def _require_provider(provider: OidcProvider | None) -> OidcProvider:
    if provider is None:
        raise NotFound("google sign-in not configured")
    return provider


@router.get("/oidc/google/start", dependencies=[Depends(limit_signin)])
def oidc_start(
    next: str | None = Query(default=None, max_length=512),
    store: AuthStore = Depends(get_auth_store),
    provider: OidcProvider | None = Depends(get_oidc_provider),
) -> RedirectResponse:
    provider = _require_provider(provider)
    s = get_settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 chars, within RFC 7636's 43..128
    binding = secrets.token_urlsafe(32)
    store.put_oidc_flow(OidcFlow(
        state=state, nonce=nonce, code_verifier=verifier,
        browser_binding_hash=hashlib.sha256(binding.encode()).hexdigest(),
        next_path=safe_next_path(next),
        expires_at=sessions.now() + timedelta(minutes=s.preauth_timeout_minutes),
    ))
    resp = RedirectResponse(
        provider.authorization_url(state=state, nonce=nonce, code_verifier=verifier),
        status_code=302,
    )
    resp.set_cookie(
        _flow_cookie_name(), binding, max_age=s.preauth_timeout_minutes * 60, path="/",
        domain=s.session_cookie_domain or None, secure=s.session_cookie_secure,
        httponly=True, samesite="lax",
    )
    return resp


@router.get("/oidc/google/callback", dependencies=[Depends(limit_signin)])
async def oidc_callback(
    request: Request,
    code: str | None = Query(default=None, max_length=2048),
    state: str | None = Query(default=None, max_length=256),
    store: AuthStore = Depends(get_auth_store),
    provider: OidcProvider | None = Depends(get_oidc_provider),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    provider = _require_provider(provider)

    def _failed() -> RedirectResponse:
        log.info("sign_in_failed", extra={"event": "oidc", "reason": "generic"})
        if not get_settings().web_origin:
            raise _fail()
        r = RedirectResponse(_web_url("/sign-in?" + urlencode({"error": "sign_in_failed"})), 302)
        r.delete_cookie(_flow_cookie_name(), path="/")
        return r

    flow = store.pop_oidc_flow(state) if state else None
    binding = request.cookies.get(_flow_cookie_name(), "")
    if (flow is None or not code or sessions.now() >= flow.expires_at
            or not hmac.compare_digest(
                hashlib.sha256(binding.encode()).hexdigest(), flow.browser_binding_hash)):
        return _failed()
    try:
        claims = await provider.exchange(code=code, code_verifier=flow.code_verifier,
                                         nonce=flow.nonce)
    except OidcError:
        return _failed()

    email = claims.get("email")
    if not email or claims.get("email_verified") is not True:
        return _failed()
    user = find_user_by_email(db, email)  # invited = a user row exists...
    ms = active_memberships(db, user.id) if user else []
    if user is None or not ms:  # ...with an active membership
        return _failed()

    token, sess = sessions.create_session(
        store, user_id=user.id, stage=sessions.ACTIVE, auth_method="oidc_google",
        active_org_id=ms[0].organization_id,
    )
    resp = RedirectResponse(_web_url(flow.next_path), status_code=302)
    resp.delete_cookie(_flow_cookie_name(), path="/")
    sessions.set_session_cookie(resp, token, sess)
    log.info("signed_in", extra={"user_id": user.id, "auth_method": "oidc_google"})
    return resp
