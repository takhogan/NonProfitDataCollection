"""Alembic environment. Pulls the DB URL from app settings and targets the
ORM metadata so `alembic revision --autogenerate` sees all models.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base  # imports all models via app/models/__init__.py

try:  # registers the PostGIS geometry type for reflection (alembic check)
    import geoalchemy2  # noqa: F401
except ImportError:  # SQLite-only demo installs
    pass

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# An explicitly configured URL (scripts/migrate.py, tests) wins over settings.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

# Objects created by raw SQL in migrations (or by PostGIS itself) that the ORM
# metadata does not describe; ignored so `alembic check` reports real drift only.
_IGNORED_TABLES = {"spatial_ref_sys"}
_SQL_ONLY_INDEXES = {"ix_area_boundary_geom", "ix_meeting_point_geom", "ix_report_location_geom"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in _IGNORED_TABLES:
        return False
    if type_ == "index" and name in _SQL_ONLY_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # needed for SQLite ALTER support
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
