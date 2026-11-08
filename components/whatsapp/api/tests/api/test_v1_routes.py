"""API-001: /v1 routes derive the org from the session; legacy routes are deprecated."""
from __future__ import annotations

from app.models.org import OrganizationMembership
from tests.api.conftest import sign_in
from tests.conftest import auth_headers

BODY = {"reference_code": "V1-1", "estimated_member_count": 3,
        "needs": [{"category": "water_delivery", "requested_quantity": 20, "unit": "liters"}]}


def test_v1_intake_read_and_list_use_session_org(client, staff, auth_store, clock):
    csrf = {"X-CSRF-Token": sign_in(client, auth_store, clock, "a@example.org")}
    r = client.post("/v1/households", json=BODY, headers=csrf)
    assert r.status_code == 201, r.text
    hh = r.json()["household_id"]
    detail = client.get(f"/v1/households/{hh}")
    assert detail.status_code == 200 and detail.json()["reference_code"] == "V1-1"
    cases = client.get("/v1/cases").json()
    assert len(cases) == 1 and cases[0]["household_id"] == hh


def test_v1_other_org_household_is_404(client, staff, auth_store, clock):
    csrf = {"X-CSRF-Token": sign_in(client, auth_store, clock, "a@example.org")}
    assert client.get(f"/v1/households/{staff['household_b']}").status_code == 404
    # Own seeded household is visible (positive control).
    assert client.get(f"/v1/households/{staff['household_a']}").status_code == 200
    # A body field cannot redirect writes into another org.
    r = client.post("/v1/households", json={**BODY, "organization_id": staff["org_b"]},
                    headers=csrf)
    assert r.status_code == 201
    assert client.get(f"/v1/households/{r.json()['household_id']}").status_code == 200


def test_switch_active_org_only_among_own_memberships(
        client, staff, auth_store, clock, db_session):
    db_session.add(OrganizationMembership(organization_id=staff["org_b"],
                                          user_id=staff["user_a"], role="reviewer"))
    db_session.commit()
    csrf = {"X-CSRF-Token": sign_in(client, auth_store, clock, "a@example.org")}
    assert client.get(f"/v1/households/{staff['household_b']}").status_code == 404
    r = client.post("/v1/me/active-organization",
                    json={"organization_id": staff["org_b"]}, headers=csrf)
    assert r.status_code == 200
    assert r.json()["active_organization_id"] == staff["org_b"]
    assert r.json()["role"] == "reviewer"
    assert client.get(f"/v1/households/{staff['household_b']}").status_code == 200
    assert client.get(f"/v1/households/{staff['household_a']}").status_code == 404


def test_switch_to_foreign_org_is_404(client, staff, auth_store, clock):
    csrf = {"X-CSRF-Token": sign_in(client, auth_store, clock, "a@example.org")}
    r = client.post("/v1/me/active-organization",
                    json={"organization_id": staff["org_b"]}, headers=csrf)
    assert r.status_code == 404


def test_v1_requires_auth(client, staff):
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/cases").status_code == 401
    assert client.post("/v1/households", json=BODY).status_code == 401


def test_dev_bearer_works_on_v1_outside_production(client, staff):
    headers = auth_headers(client, staff["login_a"])
    me = client.get("/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["auth_method"] == "dev_bearer"
    assert me.json()["csrf_token"] is None
    assert client.post("/v1/households", json=BODY, headers=headers).status_code == 201


def test_legacy_routes_carry_deprecation_headers(client, staff):
    headers = auth_headers(client, staff["login_a"])
    r = client.get(f"/orgs/{staff['org_a']}/cases", headers=headers)
    assert r.status_code == 200
    assert r.headers["deprecation"] == "true"
    assert r.headers["link"] == '</v1/cases>; rel="successor-version"'
    assert client.get("/me", headers=headers).headers["deprecation"] == "true"
    assert "deprecation" not in client.get("/v1/cases", headers=headers).headers


def test_legacy_routes_accept_cookie_sessions(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    assert client.get(f"/orgs/{staff['org_a']}/cases").status_code == 200
    assert client.get(f"/orgs/{staff['org_b']}/cases").status_code == 404


def test_fulfillment_stubs_removed(client):
    paths = set(client.app.openapi()["paths"])
    assert not any(p.startswith(("/water", "/charging")) for p in paths)
