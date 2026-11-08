"""API-012 / SEC-06: self-service and admin session revocation."""
from __future__ import annotations

from tests.api.conftest import new_client, sign_in


def test_revoke_all_ends_every_session_of_the_caller(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "a@example.org")
    laptop = new_client(client)
    sign_in(laptop, auth_store, clock, "a@example.org")
    assert len(auth_store.list_user_sessions(staff["user_a"])) == 2

    r = client.post("/v1/me/revoke-all", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert r.json() == {"revoked": 2}
    assert client.get("/v1/me").status_code == 401
    assert laptop.get("/v1/me").status_code == 401


def test_revoke_all_requires_csrf(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    assert client.post("/v1/me/revoke-all").status_code == 403
    assert client.get("/v1/me").status_code == 200


def test_admin_revokes_member_sessions_immediately(client, staff, auth_store, clock):
    victim = new_client(client)
    sign_in(victim, auth_store, clock, "a2@example.org")
    assert victim.get("/v1/me").status_code == 200

    csrf = sign_in(client, auth_store, clock, "admin@example.org")
    listed = client.get(f"/v1/admin/users/{staff['user_a2']}/sessions")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert "token_hash" not in listed.json()[0] and "csrf_token" not in listed.json()[0]

    r = client.post(f"/v1/admin/users/{staff['user_a2']}/revoke-sessions",
                    headers={"X-CSRF-Token": csrf})
    assert r.json() == {"revoked": 1}
    assert victim.get("/v1/me").status_code == 401  # next request, well within 60 s


def test_admin_cannot_revoke_user_in_other_org(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "admin@example.org")
    r = client.post(f"/v1/admin/users/{staff['user_b']}/revoke-sessions",
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404


def test_non_admin_cannot_revoke(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "a2@example.org")
    r = client.post(f"/v1/admin/users/{staff['user_a']}/revoke-sessions",
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


def test_suspended_membership_loses_access_without_new_sign_in(
        client, staff, auth_store, clock, db_session):
    from app.models.org import OrganizationMembership
    sign_in(client, auth_store, clock, "a@example.org")
    assert client.get("/v1/cases").status_code == 200
    m = db_session.query(OrganizationMembership).filter_by(user_id=staff["user_a"]).one()
    m.status = "suspended"
    db_session.commit()
    assert client.get("/v1/cases").status_code == 403
