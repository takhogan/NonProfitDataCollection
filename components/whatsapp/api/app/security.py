"""Development-only JWT bearer auth (API-014) and the legacy bcrypt hash.

The bearer token flow predates server-side sessions. It stays for local
development and the existing tests, and refuses to work in production:
`create_access_token` raises and `decode_access_token` returns None when
APP_ENV=production, and the `/auth/login` route is not mounted there.

`hash_password`/`verify_password` (bcrypt, on `user.password_hash`) back only
this dev login and the seed script. Staff password sign-in uses Argon2id
credentials in the auth store (`app.auth.credentials`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class DevAuthDisabled(RuntimeError):
    """Raised when the dev bearer flow is used in production."""


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str) -> str:
    s = get_settings()
    if s.is_production:
        raise DevAuthDisabled("JWT bearer login is development-only")
    expire = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire, "aud": "dev"}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the subject (user id), or None if invalid, expired, or in production."""
    s = get_settings()
    if s.is_production:
        return None
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], audience="dev")
    except JWTError:
        return None
    return payload.get("sub")
