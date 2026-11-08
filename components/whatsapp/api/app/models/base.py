"""Declarative base and shared column mixins.

Per PLATFORM_PLAN.md: operational records carry organization_id, created_at,
updated_at. IDs are UUIDs (stored as 36-char strings so the same models run on
SQLite locally and PostgreSQL in production).

Pilot (report-centric) tables use ``TenantOwned`` plus the helpers below:

- ``org_scoped(table, ...)`` adds ``UNIQUE (organization_id, id)`` so other
  tables can reference this one through an org-scoped composite foreign key.
- ``org_fk(table, col, target)`` builds that composite FK (DB-001): a row can
  only reference a row of the *same* organization.
- ``check_in(table, col, values)`` constrains an enumeration (DB-022).
- ``GeoType`` is a PostGIS geometry on PostgreSQL (via GeoAlchemy2) and plain
  text on SQLite, so the SQLite demo can still ``create_all``.
- ``JSONType`` is JSONB on PostgreSQL and JSON elsewhere.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


JSONType = JSON().with_variant(JSONB(), "postgresql")


class GeoType(TypeDecorator):
    """PostGIS ``geometry(<type>, <srid>)`` on PostgreSQL, ``TEXT`` elsewhere.

    Values are written as EWKT (``'SRID=4326;POINT(-66.9 10.5)'``) and read
    back as hex EWKB. Spatial predicates are written in SQL with ``ST_*``
    functions (``geoalchemy2.functions``) and only run on PostgreSQL.
    GiST indexes are created explicitly in the migration (DB-061).
    """

    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326) -> None:
        super().__init__()
        self.geometry_type = geometry_type
        self.srid = srid

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            from geoalchemy2 import Geometry

            return dialect.type_descriptor(
                Geometry(self.geometry_type, srid=self.srid, spatial_index=False)
            )
        return dialect.type_descriptor(Text())


class UUIDPk:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class OrgOwned(UUIDPk, Timestamps):
    """Mixin for tenant-owned operational records (legacy household/case slice)."""

    organization_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )


class TenantOwned(UUIDPk, Timestamps):
    """Mixin for pilot tenant tables: non-null org FK, RLS-forced in Postgres."""

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization.id"), nullable=False
    )


class AppendOnly:
    """Marker: rows are insert-only for runtime roles (DB-022/DB-053).

    The migration installs a trigger that rejects UPDATE/DELETE unless the
    current role owns the table (migration/retention role).
    """

    __append_only__ = True


def org_scoped(table: str, *extra: Any) -> tuple:
    """``__table_args__`` with the ``UNIQUE (organization_id, id)`` target."""
    return (UniqueConstraint("organization_id", "id", name=f"uq_{table}_org_id"), *extra)


def org_fk(table: str, column: str, target: str, ondelete: str | None = None,
           use_alter: bool = False) -> ForeignKeyConstraint:
    """Org-scoped composite FK: (organization_id, column) -> target(organization_id, id)."""
    return ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        name=f"fk_{table}_{column}"[:63],
        ondelete=ondelete,
        use_alter=use_alter,
    )


def _sql_list(values: Iterable[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def check_in(table: str, column: str, values: Iterable[str], nullable: bool = False
             ) -> CheckConstraint:
    expr = f"{column} IN ({_sql_list(values)})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=f"ck_{table}_{column}"[:63])
