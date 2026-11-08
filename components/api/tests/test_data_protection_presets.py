"""Data-protection preset semantics, enforced in the API (not the UI).

- standard : full records — name and full phone visible.
- protected: phone masked, name omitted.
- minimal  : aggregates only — individual records hidden.

Report rows carry no decryptable PII in the real schema (names are encrypted at
rest and not decoded in the pilot), so the masking behavior is demonstrated on
`/contacts`. The `minimal` hiding behavior is asserted on both contacts and
report detail.
"""
from tests.conftest import set_preset


def test_standard_shows_full_records(client, auth):
    set_preset(client, auth, "standard")
    contacts = client.get("/contacts", headers=auth).json()
    assert contacts, "expected contact rows"
    assert contacts[0]["name"] is not None          # full name
    assert "•" not in (contacts[0]["phone"] or "")  # full phone


def test_protected_masks_phone_and_omits_name(client, auth):
    set_preset(client, auth, "protected")
    contacts = client.get("/contacts", headers=auth).json()
    assert contacts[0]["name"] is None               # name omitted
    assert "•" in contacts[0]["phone"]               # phone masked

    # Report detail is still reachable under protected (just no decryptable PII).
    reps = client.get("/reports", headers=auth).json()
    if reps:
        detail = client.get(f"/reports/{reps[0]['id']}", headers=auth)
        assert detail.status_code == 200


def test_minimal_hides_individual_records(client, auth):
    set_preset(client, auth, "minimal")
    # Aggregates still work.
    assert client.get("/dashboard/summary", headers=auth).status_code == 200
    assert client.get("/dashboard/areas", headers=auth).status_code == 200

    # Individual records are hidden.
    assert client.get("/contacts", headers=auth).json() == []
    reps = client.get("/reports", headers=auth).json()
    if reps:
        assert client.get(f"/reports/{reps[0]['id']}", headers=auth).status_code == 404


def test_get_reflects_resolved_preset_flags(client, auth):
    set_preset(client, auth, "protected")
    cfg = client.get("/org/data-protection", headers=auth).json()
    assert cfg["preset"] == "protected"
    assert cfg["mask_phone_numbers"] is True
    assert cfg["store_names"] is False

    set_preset(client, auth, "minimal")
    assert client.get("/org/data-protection", headers=auth).json()["hide_individual_records"] is True

    set_preset(client, auth, "standard")  # reset for the demo
