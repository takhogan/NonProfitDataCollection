"""Bridge to whatsapp/api's models and the SHARED database.

The dashboard package is ``dash`` and whatsapp/api's package is ``app``, so there
is no name collision: we add whatsapp/api to ``sys.path`` and import its models
directly. The dashboard creates NO tables and NO migrations — it reuses the
intake schema and only reads (plus org-settings writes).

The dashboard uses its own engine/session against the shared DATABASE_URL and
enforces tenant scoping with explicit ``organization_id`` filters in every query.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dash.config import get_settings

# components/whatsapp/api (sibling of components/api)
_INTAKE_API_DIR = (Path(__file__).resolve().parents[2] / "whatsapp" / "api").resolve()
if str(_INTAKE_API_DIR) not in sys.path:
    sys.path.insert(0, str(_INTAKE_API_DIR))

# Shared ORM models from whatsapp/api (its package is named `app`).
import app.models as models  # noqa: E402
from app.models.base import Base  # noqa: E402,F401


def _resolve_url() -> str:
    """Resolve a relative sqlite path to an absolute one so both services point
    at the exact same file regardless of working directory."""
    url = get_settings().database_url
    prefix = "sqlite:///"
    if url.startswith(prefix):
        raw = url[len(prefix):]
        if not os.path.isabs(raw):
            raw = str((Path.cwd() / raw).resolve())
        return prefix + raw
    return url


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = _resolve_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False,
                                     expire_on_commit=False, future=True)
    return _SessionLocal


def session_scope():
    """FastAPI dependency: yield a short-lived session."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
