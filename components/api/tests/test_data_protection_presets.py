"""Data-protection preset semantics, enforced in the API (not the UI).

- standard : full records — name and full phone visible.
- protected: phone masked, name omitted.
- minimal  : aggregates only — individual records hidden.
"""
from tests.conftest import set_preset


def test_standard_shows_full_records(client, auth):
    set_preset(client, auth, "standard")
    reports = client.get("/reports", headers=auth).json()
    assert reports, "expected report rows"
    r = reports[0]
    # Full name present, phone not masked (starts with +, no bullets).
    assert r["reporter_name"] and r["reporter_name"] != ""
    assert r["reporter_phone"].startswith("+")
    assert "•" not in r["reporter_phone"]

    contacts = client.get("/contacts", headers=auth).json()
    assert contacts[0]["name"] is not None
    assert "•" not in contacts[0]["phone"]


def test_protected_masks_phone_and_omits_name(client, auth):
    set_preset(client, auth, "protected")
    r = client.get("/reports", headers=auth).json()[0]
    assert r["reporter_name"] is None          # name omitted
    assert "•" in r["reporter_phone"]          # phone masked

    contacts = client.get("/contacts", headers=auth).json()
    assert contacts[0]["name"] is None
    assert "•" in contacts[0]["phone"]

    # Detail is still available under protected (just masked).
    detail = client.get("/reports/report-1", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["reporter_name"] is None


def test_minimal_hides_individual_records(client, auth):
    set_preset(client, auth, "minimal")
    # Aggregates still work.
    assert client.get("/dashboard/summary", headers=auth).status_code == 200
    assert client.get("/dashboard/areas", headers=auth).status_code == 200

    # Individual records are hidden.
    assert client.get("/contacts", headers=auth).json() == []
    assert client.get("/reports/report-1", headers=auth).status_code == 404

    # The report LIST still returns rows but with PII stripped (no name, masked phone).
    rows = client.get("/reports", headers=auth).json()
    if rows:
        assert rows[0]["reporter_name"] is None
        assert "•" in rows[0]["reporter_phone"]


def test_get_reflects_resolved_preset_flags(client, auth):
    # After choosing protected, GET should report masking on / names off.
    set_preset(client, auth, "protected")
    cfg = client.get("/org/data-protection", headers=auth).json()
    assert cfg["preset"] == "protected"
    assert cfg["mask_phone_numbers"] is True
    assert cfg["store_names"] is False

    # minimal reports hide_individual_records.
    set_preset(client, auth, "minimal")
    cfg = client.get("/org/data-protection", headers=auth).json()
    assert cfg["hide_individual_records"] is True

    # Reset to standard so other tests/the demo start clean.
    set_preset(client, auth, "standard")
