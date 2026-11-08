"""Durable org-settings store, reusing the shared `policy_version` table.

Dashboard-managed org settings (profile, data-protection, channels, bot &
dashboard config) are stored as JSON rows in the existing policy_version table —
no new tables or migrations. Each setting is one row per org:

    kind = "other", version = "dashboard:<name>", body_json = <settings dict>

This satisfies the table's CHECK (kind) and UNIQUE (org, kind, version)
constraints, and the settings survive restarts and are shared across instances.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dash.shared_db import models, set_tenant

PolicyVersion = models.PolicyVersion
_KIND = "other"


def _ver(name: str) -> str:
    return f"dashboard:{name}"


def get_setting(db: Session, org_id: str, name: str, default: dict | None = None) -> dict | None:
    set_tenant(db, org_id)  # policy_version is row-level secured
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
    set_tenant(db, org_id)  # policy_version is row-level secured
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
