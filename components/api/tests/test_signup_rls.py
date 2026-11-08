"""Sign-up must work when the DB login does not bypass row-level security.

policy_version has FORCE ROW LEVEL SECURITY (migration 2a7c4e91d3b0). Locally
the login is the `postgres` superuser, which bypasses RLS, so the bug hid; in
prod the login is not a superuser and POST /auth/signup failed with
"new row violates row-level security policy for table policy_version" (a 500
without CORS headers, shown by the web app as "Cannot reach the server").

These tests run the API as the non-superuser group role csl_runtime.
"""
import uuid

import pytest
from sqlalchemy import text

from dash.shared_db import get_engine

pytestmark = pytest.mark.skipif(
    get_engine().dialect.name != "postgresql", reason="RLS needs PostgreSQL"
)


@pytest.fixture()
def email():
    addr = f"signup-rls-{uuid.uuid4().hex[:10]}@example.org"
    yield addr
    # Clean up as the superuser login.
    with get_engine().begin() as c:
        org_ids = [r[0] for r in c.execute(text(
            'SELECT m.organization_id FROM organization_membership m '
            'JOIN "user" u ON u.id = m.user_id WHERE u.auth_subject = :e'), {"e": addr})]
        for oid in org_ids:
            c.execute(text("DELETE FROM policy_version WHERE organization_id = :o"), {"o": oid})
            c.execute(text("DELETE FROM organization_membership WHERE organization_id = :o"),
                      {"o": oid})
        c.execute(text('DELETE FROM "user" WHERE auth_subject = :e'), {"e": addr})
        for oid in org_ids:
            c.execute(text("DELETE FROM organization WHERE id = :o"), {"o": oid})


def test_signup_under_rls_creates_org_and_settings(rls_client, email):
    r = rls_client.post("/auth/signup", json={
        "email": email, "password": "synthetic-pass-1", "display_name": "Test Admin",
        "org_name": "Synthetic Community Org", "org_type": "community",
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # The stored profile is readable back through RLS (not the default).
    p = rls_client.get("/org/profile", headers=headers)
    assert p.status_code == 200, p.text
    assert p.json()["name"] == "Synthetic Community Org"

    with get_engine().connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM policy_version pv JOIN organization_membership m "
            "ON m.organization_id = pv.organization_id JOIN \"user\" u ON u.id = m.user_id "
            "WHERE u.auth_subject = :e AND pv.version LIKE 'dashboard:%'"), {"e": email}).scalar()
    assert n == 3
