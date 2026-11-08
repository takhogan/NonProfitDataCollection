from tests.conftest import auth_headers

INTAKE_BODY = {
    "reference_code": "A-INTAKE-1",
    "estimated_member_count": 5,
    "contacts": [
        {"preferred_name": "Carmen", "preferred_language": "es", "relationship_label": "head"},
    ],
    "source_channel": "volunteer_assisted",
    "reporting_relationship": "household",
    "answers": {"remaining_drinking_water": "poca"},
    "observations": [
        {"service_type": "piped_water", "status": "unavailable"},
        {"service_type": "electricity", "status": "intermittent"},
    ],
    "needs": [
        {"category": "water_delivery", "requested_quantity": 40, "unit": "liters", "urgency": "urgent"},
        {"category": "charging_access", "requested_quantity": 2, "unit": "device_sessions"},
    ],
}


def _org_url(seeded, path=""):
    return f"/orgs/{seeded['org_a']}/households{path}"


def test_create_intake_creates_household_case_and_needs(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    resp = client.post(_org_url(seeded), json=INTAKE_BODY, headers=headers)
    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["household_id"]
    assert result["case_id"]
    assert result["assessment_id"]
    assert len(result["need_ids"]) == 2

    # Retrieve the household with its contacts and cases.
    detail = client.get(_org_url(seeded, f"/{result['household_id']}"), headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["reference_code"] == "A-INTAKE-1"
    assert len(body["contacts"]) == 1
    assert body["contacts"][0]["preferred_name"] == "Carmen"
    assert len(body["cases"]) == 1
    case = body["cases"][0]
    assert case["status"] == "open"
    # Water in liters and charging in device sessions stay separate.
    cats = {n["category"]: n for n in case["needs"]}
    assert cats["water_delivery"]["unit"] == "liters"
    assert cats["charging_access"]["unit"] == "device_sessions"
    assert cats["charging_access"]["status"] == "requested"


def test_list_cases_for_org(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    client.post(_org_url(seeded), json=INTAKE_BODY, headers=headers)
    resp = client.get(f"/orgs/{seeded['org_a']}/cases", headers=headers)
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 1
    assert cases[0]["household_id"]
    assert cases[0]["status"] == "open"


def test_duplicate_reference_code_conflicts(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    client.post(_org_url(seeded), json=INTAKE_BODY, headers=headers)
    resp = client.post(_org_url(seeded), json=INTAKE_BODY, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


def test_need_unit_mismatch_rejected(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    bad = {**INTAKE_BODY, "reference_code": "A-BAD-UNIT",
           "needs": [{"category": "water_delivery", "unit": "device_sessions"}]}
    resp = client.post(_org_url(seeded), json=bad, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_failed"
