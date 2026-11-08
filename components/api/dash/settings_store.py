"""Durable org-settings store, reusing the shared `policy_version` table.

Dashboard-managed org settings (profile, data-protection, channels, bot &
dashboard config) are stored as JSON rows in the existing policy_version table —
no new tables or migrations. Each setting is one row per org:

    kind = "other", version = "dashboard:<name>", body_json = <settings dict>

This satisfies the table's CHECK (kind) and UNIQUE (org, kind, version)
constraints, and the settings survive restarts and are shared across instances.
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dash.shared_db import models

PolicyVersion = models.PolicyVersion
_KIND = "other"


def _ver(name: str) -> str:
    return f"dashboard:{name}"


def _scope_to_org(db: Session, org_id: str) -> None:
    """Set the RLS tenant (``app.org_id``) for the current transaction.

    policy_version has FORCE ROW LEVEL SECURITY with ``organization_id =
    app_current_org()`` (migration 2a7c4e91d3b0). Unless the login is a
    superuser, reads see no rows and inserts fail without this. The setting is
    transaction-local, so it resets at COMMIT/ROLLBACK.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.org_id', :org, true)"), {"org": str(org_id)})


def get_setting(db: Session, org_id: str, name: str, default: dict | None = None) -> dict | None:
    _scope_to_org(db, org_id)
    row = db.scalar(
        select(PolicyVersion).where(
            PolicyVersion.organization_id == org_id,
            PolicyVersion.kind == _KIND,
            PolicyVersion.version == _ver(name),
        )
    )
    if row is None:
        return dict(default) if default is not None else None
    return dict(row.body_json or {})


def put_setting(db: Session, org_id: str, name: str, body: dict, *,
                commit: bool = True) -> dict:
    _scope_to_org(db, org_id)
    row = db.scalar(
        select(PolicyVersion).where(
            PolicyVersion.organization_id == org_id,
            PolicyVersion.kind == _KIND,
            PolicyVersion.version == _ver(name),
        )
    )
    if row is None:
        row = PolicyVersion(organization_id=org_id, kind=_KIND, version=_ver(name),
                            body_json=dict(body))
        db.add(row)
    else:
        row.body_json = dict(body)
    if commit:
        db.commit()
    else:
        db.flush()
    return dict(body)
