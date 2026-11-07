"""Test harness: isolated SQLite DB, seeded two-org fixture, auth helpers."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models import Base
from app.models.household import Household, Person
from app.models.org import Organization, OrganizationMembership, User
from app.security import hash_password


@pytest.fixture()
def db_session():
    # A single shared in-memory connection (StaticPool) so the TestClient and
    # the test body see the same database.
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def seeded(db_session):
    """Two orgs, one user each, plus a sample household per org.

    Returns a dict with ids and login credentials for use in tests.
    """
    org_a = Organization(name="Org A")
    org_b = Organization(name="Org B")
    db_session.add_all([org_a, org_b])
    db_session.flush()

    user_a = User(auth_subject="a@example.org", display_name="Ana (A)",
                  password_hash=hash_password("secret-a"))
    user_b = User(auth_subject="b@example.org", display_name="Beto (B)",
                  password_hash=hash_password("secret-b"))
    db_session.add_all([user_a, user_b])
    db_session.flush()

    mem_a = OrganizationMembership(organization_id=org_a.id, user_id=user_a.id,
                                   role="coordinator")
    mem_b = OrganizationMembership(organization_id=org_b.id, user_id=user_b.id,
                                   role="coordinator")
    db_session.add_all([mem_a, mem_b])

    hh_a = Household(organization_id=org_a.id, reference_code="A-001",
                     estimated_member_count=4)
    hh_b = Household(organization_id=org_b.id, reference_code="B-001",
                     estimated_member_count=3)
    db_session.add_all([hh_a, hh_b])
    db_session.commit()

    return {
        "org_a": org_a.id, "org_b": org_b.id,
        "user_a": user_a.id, "user_b": user_b.id,
        "household_a": hh_a.id, "household_b": hh_b.id,
        "login_a": {"email": "a@example.org", "password": "secret-a"},
        "login_b": {"email": "b@example.org", "password": "secret-b"},
    }


@pytest.fixture()
def client(db_session):
    """TestClient wired to the test session via get_db override."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth_headers(client: TestClient, login: dict) -> dict:
    resp = client.post("/auth/login", json=login)
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
