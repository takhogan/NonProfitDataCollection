"""Database engine, session factory, and FastAPI session dependency."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _make_engine(url: str):
    # check_same_thread is a SQLite-only argument; needed because TestClient
    # and the dev server may touch the connection from different threads.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite") and url not in ("sqlite://", "sqlite:///:memory:"):
        # Ensure the parent directory for a file-based SQLite DB exists.
        path = url.split("sqlite:///", 1)[-1]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
