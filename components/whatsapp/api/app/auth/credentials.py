"""Password (Argon2id) and TOTP verification with lockout.

Sign-in errors are generic: unknown email, wrong password, locked account and
wrong TOTP code all produce the same `unauthenticated` response, and an
unknown email still costs one Argon2 verification so timing does not reveal
which emails exist.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.auth import sessions
from app.auth.store import AuthStore, PasswordCredential, TotpSecret
from app.config import get_settings
from app.errors import ValidationError

# argon2-cffi defaults to Argon2id with RFC 9106 "low memory" parameters.
_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-password")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def set_password(store: AuthStore, user_id: str, password: str) -> None:
    """Set or replace a user's password (admin/invite flows and seeding).

    TODO(API-010): add the breached-password check (k-anonymity range query)
    once outbound HTTP from the API is approved for this deployment.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            "password too short", details={"min_length": MIN_PASSWORD_LENGTH},
            message_key="errors.password_too_short",
        )
    store.put_password(
        PasswordCredential(user_id=user_id, password_hash=hash_password(password),
                           updated_at=sessions.now())
    )


def is_locked(store: AuthStore, user_id: str) -> bool:
    cred = store.get_password(user_id)
    if cred is None or cred.locked_until is None:
        return False
    lu = cred.locked_until
    return sessions.now() < (lu if lu.tzinfo else lu.replace(tzinfo=sessions.now().tzinfo))


def register_failure(store: AuthStore, user_id: str) -> None:
    cred = store.get_password(user_id)
    if cred is None:
        return
    s = get_settings()
    count = cred.failed_count + 1
    if count >= s.password_max_failures:
        cred = replace(cred, failed_count=0,
                       locked_until=sessions.now() + timedelta(minutes=s.password_lockout_minutes))
    else:
        cred = replace(cred, failed_count=count)
    store.put_password(cred)


def clear_failures(store: AuthStore, user_id: str) -> None:
    """Reset the failure counter. Called only after a *complete* sign-in
    (password and TOTP), so password-correct/TOTP-wrong cycles keep counting."""
    cred = store.get_password(user_id)
    if cred is not None and (cred.failed_count or cred.locked_until):
        store.put_password(replace(cred, failed_count=0, locked_until=None))


def check_password(store: AuthStore, user_id: str | None, password: str) -> bool:
    """True only for an existing, unlocked user with the right password."""
    cred = store.get_password(user_id) if user_id else None
    if cred is None:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False
    if is_locked(store, cred.user_id):
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except VerificationError:
            pass
        return False
    try:
        _hasher.verify(cred.password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        register_failure(store, cred.user_id)
        return False
    if _hasher.check_needs_rehash(cred.password_hash):
        cred = replace(cred, password_hash=hash_password(password))
        store.put_password(cred)
    return True


# --- TOTP -------------------------------------------------------------------

def start_totp_enrollment(store: AuthStore, user_id: str) -> str:
    """Create (or reuse an unconfirmed) secret and return it."""
    existing = store.get_totp(user_id)
    if existing is not None and existing.confirmed_at is None:
        return existing.secret
    if existing is not None:
        raise ValidationError("totp already enrolled", message_key="errors.totp_already_enrolled")
    secret = pyotp.random_base32()
    store.put_totp(TotpSecret(user_id=user_id, secret=secret))
    return secret


def provisioning_uri(secret: str, account_label: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_label, issuer_name=get_settings().totp_issuer
    )


def verify_totp(store: AuthStore, user_id: str, code: str, *, enrolling: bool) -> bool:
    """Accept a 6-digit code within ±1 step, once. Confirms enrollment on success."""
    t = store.get_totp(user_id)
    if t is None or (t.confirmed_at is None) != enrolling:
        return False
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    totp = pyotp.TOTP(t.secret)
    ts = sessions.now().timestamp()
    step_now = int(ts // totp.interval)
    for offset in (-1, 0, 1):
        step = step_now + offset
        if step <= t.last_used_step:
            continue
        if pyotp.utils.strings_equal(totp.at(step * totp.interval), code):
            store.put_totp(replace(
                t, last_used_step=step,
                confirmed_at=t.confirmed_at or sessions.now(),
            ))
            return True
    return False
