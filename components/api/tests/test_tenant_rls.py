"""Dashboard reads of RLS tables must see the caller's org on a non-bypass login.

report, observation, need, area and policy_version have FORCE ROW LEVEL SECURITY
keyed on app.org_id (and app.role for staff-only tables). Without the tenant set
on every transaction, prod returned empty lists and PATCH /reports/{id} gave a
404 (its re-read runs after a commit, in a new transaction).
"""
import pytest

from dash.shared_db import get_engine

pytestmark = pytest.mark.skipif(
    get_engine().dialect.name != "postgresql", reason="RLS needs PostgreSQL"
)


@pytest.fixture()
def rls_auth(rls_client):
    r = rls_client.post("/auth/login", json={"email": "demo@metron.org", "password": "demo-pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_reports_visible_under_rls(rls_client, rls_auth):
    r = rls_client.get("/reports", headers=rls_auth)
    assert r.status_code == 200, r.text
    assert len(r.json()) > 0
    areas = rls_client.get("/dashboard/areas", headers=rls_auth)
    assert areas.status_code == 200 and len(areas.json()) > 0


def test_patch_report_rereads_after_commit_under_rls(rls_client, rls_auth):
    rid = rls_client.get("/reports", headers=rls_auth).json()[0]["id"]
    before = rls_client.get(f"/reports/{rid}", headers=rls_auth).json()
    try:
        r = rls_client.patch(f"/reports/{rid}", headers=rls_auth, json={"notes": "rls check"})
        assert r.status_code == 200, r.text
        assert r.json()["notes"] == "rls check"
    finally:
        rls_client.patch(f"/reports/{rid}", headers=rls_auth, json={"notes": before["notes"]})
