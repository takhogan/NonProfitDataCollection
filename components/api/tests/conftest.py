import os

import pytest

# Point at the shared seeded SQLite DB before the app/config import reads it.
os.environ.setdefault(
    "DATABASE_URL", "sqlite:///../whatsapp/api/local-data/aid.sqlite3"
)

from fastapi.testclient import TestClient  # noqa: E402

from dash.main import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth(client):
    tok = client.post("/auth/login",
                      json={"email": "demo@metron.org", "password": "demo-pass"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def set_preset(client, headers, preset: str):
    """Set the org's data-protection preset and return the resolved config."""
    body = {
        "preset": preset, "store_names": True, "location_precision": "precise",
        "raw_message_retention_days": 90, "mask_phone_numbers": False,
        "redact_exports": False, "individual_records_roles": ["org_admin"],
        "audit_log_enabled": True,
    }
    return client.put("/org/data-protection", headers=headers, json=body).json()


@pytest.fixture()
def rls_client(client):
    """TestClient whose DB sessions run as csl_runtime, which cannot bypass
    row-level security (like the prod login). Locally `postgres` is a superuser
    and bypasses RLS, which hides missing tenant context."""
    from dash.deps import get_db
    from dash.shared_db import get_sessionmaker

    def _db():
        db = get_sessionmaker()()
        db.connection().exec_driver_sql("SET ROLE csl_runtime")
        db.commit()  # session-level SET ROLE survives the commit
        try:
            yield db
        finally:
            db.rollback()
            db.connection().exec_driver_sql("RESET ROLE")
            db.commit()
            db.close()

    app.dependency_overrides[get_db] = _db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
