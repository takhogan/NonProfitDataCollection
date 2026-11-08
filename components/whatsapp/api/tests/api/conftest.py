"""Fixtures for the /v1 API tests: a controllable clock, staff credentials,
and a password + TOTP sign-in helper."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth import credentials, sessions
from app.models.org import OrganizationMembership, User
from app.security import hash_password

PASSWORDS = {
    "a@example.org": "correct horse battery A",
    "b@example.org": "correct horse battery B",
    "admin@example.org": "correct horse battery Z",
    "a2@example.org": "correct horse battery A2",
}


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(sessions, "now", c)
    return c


@pytest.fixture(autouse=True)
def generous_rate_limits(monkeypatch):
    """Rate limits are tested on their own; keep them out of other tests' way."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_signin_per_minute", 10_000)


@pytest.fixture()
def staff(seeded, db_session, auth_store):
    """Argon2 passwords for users A and B, plus an admin and a second user in org A."""
    admin = User(auth_subject="admin@example.org", display_name="Admin A",
                 password_hash=hash_password("unused"))
    a2 = User(auth_subject="a2@example.org", display_name="Second A",
              password_hash=hash_password("unused"))
    db_session.add_all([admin, a2])
    db_session.flush()
    db_session.add_all([
        OrganizationMembership(organization_id=seeded["org_a"], user_id=admin.id,
                               role="administrator"),
        OrganizationMembership(organization_id=seeded["org_a"], user_id=a2.id,
                               role="caseworker"),
    ])
    db_session.commit()
    ids = {"a@example.org": seeded["user_a"], "b@example.org": seeded["user_b"],
           "admin@example.org": admin.id, "a2@example.org": a2.id}
    for email, uid in ids.items():
        credentials.set_password(auth_store, uid, PASSWORDS[email])
    return {**seeded, "admin": admin.id, "user_a2": a2.id, "ids": ids}


def sign_in(client: TestClient, auth_store, clock: Clock, email: str) -> str:
    """Password + TOTP (enrolling on first use). Returns the active CSRF token."""
    r = client.post("/v1/auth/password/login",
                    json={"email": email, "password": PASSWORDS[email]})
    assert r.status_code == 200, r.text
    step = r.json()
    csrf = {"X-CSRF-Token": step["csrf_token"]}
    if step["stage"] == "totp_enroll":
        e = client.post("/v1/auth/totp/enroll", headers=csrf)
        assert e.status_code == 200, e.text
        secret = e.json()["secret"]
    else:
        uid = auth_store.get_session_by_token_hash(
            sessions.hash_token(client.cookies.get(sessions.cookie_name()))).user_id
        secret = auth_store.get_totp(uid).secret
    clock.advance(seconds=31)  # a fresh TOTP step, so codes are never replays
    code = pyotp.TOTP(secret).at(clock())
    v = client.post("/v1/auth/totp/verify", json={"code": code}, headers=csrf)
    assert v.status_code == 200, v.text
    assert v.json()["stage"] == "active"
    return v.json()["csrf_token"]


def new_client(client: TestClient) -> TestClient:
    """A second browser (own cookie jar) against the same app and overrides."""
    return TestClient(client.app, base_url="https://testserver")
