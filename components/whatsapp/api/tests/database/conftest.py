"""PostgreSQL/PostGIS integration fixtures for the database component (DB-092).

Tests here need a real PostgreSQL 15 + PostGIS server; they create and drop
their own throwaway databases on it. Point ``TEST_POSTGRES_URL`` at a server
maintenance database (``.../postgres``) with a role allowed to CREATE DATABASE
and CREATE ROLE; by default the Docker Compose server is tried:

    docker compose up -d db
    TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres-local-only@localhost:55432/postgres \
        .venv/bin/python -m pytest tests/database

Without a reachable server every test in this package is skipped (SQLite is
for quick demos only: RLS, triggers, SKIP LOCKED, and spatial behavior are
not testable there).
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.database._pg import (  # noqa: E402
    _SERVER, alembic_config, scratch_database,
)


def pytest_collection_modifyitems(config, items):
    if _SERVER is None:
        skip = pytest.mark.skip(reason="PostgreSQL not reachable (set TEST_POSTGRES_URL)")
        for item in items:
            if "tests/database" in str(item.fspath).replace(os.sep, "/"):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_url():
    with scratch_database() as url:
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def engine(migrated_url):
    eng = create_engine(migrated_url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session")
def seeded(session_factory, engine):
    """Run the DB-090 seed once; return ids useful to tests (read as owner)."""
    from scripts.seed import seed

    summary = seed(session_factory)
    org_ids = summary["org_ids"]
    with engine.connect() as c:  # owner/superuser: bypasses RLS for fixture lookups
        def one(sql, **kw):
            return c.execute(text(sql), kw).scalar_one()

        def membership(email):
            return c.execute(text(
                'SELECT m.id FROM organization_membership m JOIN "user" u ON u.id = m.user_id '
                "WHERE u.auth_subject = :e"), {"e": email}).scalar_one()

        def provider(org, name):
            return c.execute(text(
                "SELECT p.id, m.id FROM provider_organization p JOIN organization_membership m "
                "ON m.provider_organization_id = p.id WHERE p.organization_id = :o "
                "AND p.name = :n"), {"o": org, "n": name}).one()

        prot, std = org_ids["luzviva"], org_ids["aguazul"]
        data = {
            "protective": prot,
            "standard": std,
            "prot_coordinator": membership("maria@luzviva.org"),
            "prot_volunteer": membership("voluntaria@luzviva.org"),
            "std_coordinator": membership("ana@aguazul.org"),
            "prot_vetted": provider(prot, "Cisternas Solidarias (demo)"),
            "prot_unvetted": provider(prot, "Brigada Nueva (demo)"),
            "std_vetted": provider(std, "Cisternas Solidarias (demo)"),
            "prot_profile": one("SELECT id FROM privacy_profile_version WHERE organization_id=:o",
                                o=prot),
            "std_profile": one("SELECT id FROM privacy_profile_version WHERE organization_id=:o",
                               o=std),
            "prot_sector": one("SELECT id FROM area WHERE organization_id=:o AND type='sector' "
                               "ORDER BY official_code LIMIT 1", o=prot),
            "std_sector": one("SELECT id FROM area WHERE organization_id=:o AND type='sector' "
                              "ORDER BY official_code LIMIT 1", o=std),
            "prot_report": one("SELECT id FROM report WHERE organization_id=:o "
                               "AND reporter_key_id IS NOT NULL LIMIT 1", o=prot),
            "std_report": one("SELECT id FROM report WHERE organization_id=:o "
                              "AND reporter_key_id IS NOT NULL LIMIT 1", o=std),
        }
    return data


@pytest.fixture()
def tx(session_factory):
    """Open a tenant transaction on a fresh session: tx(org, actor, role, ...)."""
    from app.db import tenant_transaction

    sessions: list[Session] = []

    @contextmanager
    def _open(org_id, actor_id, role, **kw):
        s = session_factory()
        sessions.append(s)
        with tenant_transaction(org_id, actor_id, role, session=s, **kw) as db:
            yield db

    yield _open
    for s in sessions:
        s.close()
