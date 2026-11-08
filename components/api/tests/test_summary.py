"""The dashboard summary is plain-language, built from the real metrics (no LLM)."""
from dash.routers.dashboard import _build_summary


def test_summary_mentions_real_numbers_and_areas():
    s = _build_summary("Miami Mutual Aid",
                       {"reports_today": 50, "without_power": 57, "without_water": 46, "urgent": 12},
                       [{"area": "Liberty City"}, {"area": "Little Haiti"}])
    assert "50 reports" in s
    assert "57 households without power" in s
    assert "46 without water" in s
    assert "12 reports need urgent review" in s
    assert "Liberty City and Little Haiti" in s


def test_summary_empty_org():
    s = _build_summary("New NGO", {"reports_today": 0, "without_power": 0,
                                   "without_water": 0, "urgent": 0}, [])
    assert "No new reports" in s


def test_summary_all_clear_and_singular():
    s = _build_summary("Tiny Org", {"reports_today": 1, "without_power": 1,
                                    "without_water": 0, "urgent": 1}, [{"area": "Overtown"}])
    assert "1 report came in" in s          # singular report
    assert "1 household without power" in s  # singular household
    assert "1 report needs urgent review" in s
    s2 = _build_summary("Calm", {"reports_today": 3, "without_power": 0,
                                 "without_water": 0, "urgent": 0}, [])
    assert "No power or water outages" in s2
    assert "Nothing is flagged urgent" in s2


def test_summary_live_endpoint(client, auth):
    r = client.get("/dashboard/summary", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # The sentence references the real metric numbers.
    assert str(body["metrics"]["without_power"]) in body["summary"] or \
        body["metrics"]["reports_today"] == 0
