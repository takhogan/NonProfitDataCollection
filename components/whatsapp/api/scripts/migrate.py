"""Run Alembic migrations as a one-off step (Cloud Run Job, not at boot).

    python -m scripts.migrate            # upgrade to head
    python -m scripts.migrate <revision> # upgrade/downgrade to a specific rev

Migrations are intentionally NOT run on container start: multiple API/worker
instances booting at once must not race on DDL. Run this once per deploy.
"""
from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config

from app.config import get_settings


def run(revision: str = "head") -> None:
    settings = get_settings()
    settings.validate_runtime()

    cfg = Config("alembic.ini")
    # env.py reads DATABASE_URL from settings, but set it explicitly too so this
    # works regardless of cwd nuances.
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, revision)
    print(f"migrations applied: {revision}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "head")
