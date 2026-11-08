"""API-010 password + TOTP sign-in, SEC-05 session cookie and timeouts."""
from __future__ import annotations

import pyotp

from app.auth import sessions
from tests.api.conftest import PASSWORDS, sign_in

LOGIN = "/v1/auth/password/login"


def test_full_password_totp_flow_creates_cookie_session(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "a@example.org")
    me = client.get("/v1/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["auth_method"] == "session"
    assert body["active_organization_id"] == staff["org_a"]
    assert body["role"] == "coordinator"
    assert body["memberships"][0]["organization_name"] == "Org A"
    assert body["csrf_token"] == csrf
    assert body["session"]["auth_method"] == "password_totp"
    assert body["session"]["idle_timeout_seconds"] == 1800
    assert me.headers["cache-control"] == "no-store"


def test_session_cookie_attributes(client, staff, auth_store, clock):
    r = client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Host-sid=")
    low = cookie.lower()
    assert "httponly" in low and "secure" in low and "samesite=lax" in low and "path=/" in low
    assert "domain=" not in low


def test_token_rotates_after_totp_and_store_keeps_only_hash(client, staff, auth_store, clock):
    client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    preauth = client.cookies.get(sessions.cookie_name())
    sign_in(client, auth_store, clock, "a@example.org")
    active = client.cookies.get(sessions.cookie_name())
    assert active != preauth
    assert auth_store.get_session_by_token_hash(sessions.hash_token(preauth)) is None
    assert auth_store.get_session_by_token_hash(active) is None  # raw token never a key
    assert auth_store.get_session_by_token_hash(sessions.hash_token(active)) is not None


def test_preauth_session_cannot_use_api(client, staff):
    client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    assert client.get("/v1/me").status_code == 401


def test_errors_are_generic(client, staff):
    wrong = client.post(LOGIN, json={"email": "a@example.org", "password": "nope-nope-nope"})
    unknown = client.post(LOGIN, json={"email": "ghost@example.org", "password": "nope-nope-nope"})
    for r in (wrong, unknown):
        assert r.status_code == 401
        j = r.json()
        assert j["code"] == "unauthenticated"
        assert j["message_key"] == "errors.sign_in_failed"
        assert j["details"] is None
    assert "set-cookie" not in wrong.headers


def test_lockout_after_repeated_failures(client, staff, clock):
    for _ in range(5):
        client.post(LOGIN, json={"email": "a@example.org", "password": "wrong-password!"})
    good = {"email": "a@example.org", "password": PASSWORDS["a@example.org"]}
    locked = client.post(LOGIN, json=good)
    assert locked.status_code == 401
    assert locked.json()["message_key"] == "errors.sign_in_failed"  # same as a wrong password
    clock.advance(minutes=16)
    assert client.post(LOGIN, json=good).status_code == 200


def test_wrong_and_replayed_totp_rejected(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")  # enrolls
    client.post("/v1/auth/logout", headers={"X-CSRF-Token": client.get("/v1/me").json()["csrf_token"]})

    r = client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    assert r.json()["stage"] == "totp_verify"
    csrf = {"X-CSRF-Token": r.json()["csrf_token"]}
    bad = client.post("/v1/auth/totp/verify", json={"code": "000000"}, headers=csrf)
    assert bad.status_code == 401
    # The code accepted at enrollment (same step window) cannot be replayed.
    secret = auth_store.get_totp(staff["user_a"]).secret
    replay = pyotp.TOTP(secret).at(clock())
    assert client.post("/v1/auth/totp/verify", json={"code": replay}, headers=csrf).status_code == 401


def test_totp_failures_count_toward_lockout(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    for _ in range(5):
        r = client.post(LOGIN, json={"email": "a@example.org",
                                     "password": PASSWORDS["a@example.org"]})
        if r.status_code != 200:
            break
        client.post("/v1/auth/totp/verify", json={"code": "123456"},
                    headers={"X-CSRF-Token": r.json()["csrf_token"]})
    r = client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    assert r.status_code == 401


def test_user_without_active_membership_cannot_sign_in(client, staff, db_session):
    from app.models.org import OrganizationMembership
    m = db_session.query(OrganizationMembership).filter_by(user_id=staff["user_a"]).one()
    m.status = "suspended"
    db_session.commit()
    r = client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    assert r.status_code == 401


def test_idle_timeout(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    clock.advance(minutes=29)
    assert client.get("/v1/me").status_code == 200  # activity resets idle timer
    clock.advance(minutes=29)
    assert client.get("/v1/me").status_code == 200
    clock.advance(minutes=31)
    assert client.get("/v1/me").status_code == 401


def test_absolute_timeout_despite_activity(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    start = clock()
    for _ in range(40):  # 12 hours of activity every 20 minutes
        clock.advance(minutes=20)
        last = client.get("/v1/me").status_code
        if last == 401:
            break
    assert last == 401
    elapsed = clock() - start
    assert 11.5 * 3600 <= elapsed.total_seconds() <= 12.5 * 3600


def test_preauth_expires_after_five_minutes(client, staff, clock):
    r = client.post(LOGIN, json={"email": "a@example.org", "password": PASSWORDS["a@example.org"]})
    clock.advance(minutes=6)
    e = client.post("/v1/auth/totp/enroll", headers={"X-CSRF-Token": r.json()["csrf_token"]})
    assert e.status_code == 401


def test_logout_ends_session(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "a@example.org")
    r = client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert auth_store.list_user_sessions(staff["user_a"]) == []
    assert client.get("/v1/me").status_code == 401


def test_dev_adopts_seed_password_but_still_requires_totp(client, seeded, auth_store):
    r = client.post(LOGIN, json=seeded["login_a"])  # bcrypt seed password, no Argon2 yet
    assert r.status_code == 200 and r.json()["stage"] == "totp_enroll"
    assert auth_store.get_password(seeded["user_a"]).password_hash.startswith("$argon2id$")
    assert client.get("/v1/me").status_code == 401


def test_seed_password_not_adopted_in_production(client, seeded, auth_store, monkeypatch):
    from app import config
    monkeypatch.setattr(config.get_settings(), "app_env", "production")
    assert client.post(LOGIN, json=seeded["login_a"]).status_code == 401
    assert auth_store.get_password(seeded["user_a"]) is None
