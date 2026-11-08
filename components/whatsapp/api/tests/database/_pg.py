"""Shared PostgreSQL test helpers (see conftest.py)."""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_URL = "postgresql+psycopg://postgres:postgres-local-only@localhost:55432/postgres"
PREVIOUS_REVISION = "1eb5e1be9f8b"
HEAD_REVISION = "2a7c4e91d3b0"


def _server_url() -> str | None:
    url = os.environ.get("TEST_POSTGRES_URL", DEFAULT_URL)
    try:
        eng = create_engine(url, connect_args={"connect_timeout": 3})
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return url
    except Exception:  # noqa: BLE001 - any failure means "no server"
        return None


_SERVER = _server_url()

requires_pg = pytest.mark.skipif(
    _SERVER is None, reason="PostgreSQL not reachable (set TEST_POSTGRES_URL); SQLite demo mode"
)


@contextmanager
def scratch_database(prefix: str = "csl_test"):
    """Create an empty database; yield its URL; drop it afterwards."""
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    admin = create_engine(_SERVER, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(_SERVER).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def count(db: Session, sql: str, **params) -> int:
    return db.execute(text(sql), params).scalar_one()
