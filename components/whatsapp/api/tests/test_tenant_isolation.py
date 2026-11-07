"""Cross-organization isolation: a user from org A cannot read or write org B's
data, and vice versa. These are the key security tests for the pilot gate
"one organization cannot read another's records".
"""
from tests.conftest import auth_headers

INTAKE_BODY = {
    "reference_code": "ISO-1",
    "estimated_member_count": 2,
    "needs": [{"category": "water_delivery", "requested_quantity": 20, "unit": "liters"}],
}


def _create_household_in(client, seeded, org_key, login_key, ref):
    headers = auth_headers(client, seeded[login_key])
    body = {**INTAKE_BODY, "reference_code": ref}
    resp = client.post(f"/orgs/{seeded[org_key]}/households", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["household_id"], headers


def test_user_cannot_act_in_foreign_org_path(client, seeded):
    # User A authenticates, but targets org B in the URL -> 404 (not 403), so we
    # do not even reveal that org B exists to a non-member.
    headers_a = auth_headers(client, seeded["login_a"])
    resp = client.get(f"/orgs/{seeded['org_b']}/cases", headers=headers_a)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_user_cannot_create_in_foreign_org(client, seeded):
    headers_a = auth_headers(client, seeded["login_a"])
    resp = client.post(
        f"/orgs/{seeded['org_b']}/households", json=INTAKE_BODY, headers=headers_a
    )
    assert resp.status_code == 404


def test_user_cannot_read_foreign_household_even_in_own_org_path(client, seeded):
    # B creates a household in org B.
    hh_b, _ = _create_household_in(client, seeded, "org_b", "login_b", "B-SECRET")
    headers_a = auth_headers(client, seeded["login_a"])

    # A tries to read B's household id, but through A's OWN org path. The org
    # scope on the query means the row is not found -> 404.
    resp = client.get(f"/orgs/{seeded['org_a']}/households/{hh_b}", headers=headers_a)
    assert resp.status_code == 404

    # And A cannot read it by pointing at org B's path either (not a member).
    resp2 = client.get(f"/orgs/{seeded['org_b']}/households/{hh_b}", headers=headers_a)
    assert resp2.status_code == 404


def test_cases_lists_are_isolated(client, seeded):
    # Each org creates one household/case.
    _create_household_in(client, seeded, "org_a", "login_a", "A-OWN")
    _create_household_in(client, seeded, "org_b", "login_b", "B-OWN")

    headers_a = auth_headers(client, seeded["login_a"])
    headers_b = auth_headers(client, seeded["login_b"])

    cases_a = client.get(f"/orgs/{seeded['org_a']}/cases", headers=headers_a).json()
    cases_b = client.get(f"/orgs/{seeded['org_b']}/cases", headers=headers_b).json()

    # Exactly one case each, and the household ids do not cross over.
    assert len(cases_a) == 1
    assert len(cases_b) == 1
    a_households = {c["household_id"] for c in cases_a}
    b_households = {c["household_id"] for c in cases_b}
    assert a_households.isdisjoint(b_households)


def test_owner_can_read_own_household(client, seeded):
    # Positive control: the owning org CAN read its own data.
    hh_a, headers_a = _create_household_in(client, seeded, "org_a", "login_a", "A-OWN-2")
    resp = client.get(f"/orgs/{seeded['org_a']}/households/{hh_a}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["reference_code"] == "A-OWN-2"
