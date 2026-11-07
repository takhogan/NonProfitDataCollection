from tests.conftest import auth_headers

BODY = {
    "reference_code": "IDEM-1",
    "needs": [{"category": "water_delivery", "requested_quantity": 30, "unit": "liters"}],
}


def test_same_key_replays_without_duplicating(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    url = f"/orgs/{seeded['org_a']}/households"
    key_headers = {**headers, "Idempotency-Key": "abc-123"}

    first = client.post(url, json=BODY, headers=key_headers)
    assert first.status_code == 201
    second = client.post(url, json=BODY, headers=key_headers)
    assert second.status_code == 201
    # Same household/case returned, not a new one.
    assert first.json() == second.json()

    # Only one case exists for the org.
    cases = client.get(f"/orgs/{seeded['org_a']}/cases", headers=headers).json()
    assert len(cases) == 1


def test_no_key_without_dup_guard_conflicts_on_same_reference(client, seeded):
    # Without an idempotency key, a retry of the same reference_code is a real
    # conflict (the dedupe guard is the key, the ref-code uniqueness is a backstop).
    headers = auth_headers(client, seeded["login_a"])
    url = f"/orgs/{seeded['org_a']}/households"
    assert client.post(url, json=BODY, headers=headers).status_code == 201
    assert client.post(url, json=BODY, headers=headers).status_code == 409
