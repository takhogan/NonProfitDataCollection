"""DB-091: migrations run from empty and from the previous revision."""
from __future__ import annotations

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from app.models import Base
from tests.database._pg import alembic_config, requires_pg, scratch_database

pytestmark = requires_pg

PREVIOUS = "1eb5e1be9f8b"

# Tables with a non-null organization_id that are intentionally NOT RLS-forced yet
# (identity tables used before tenant context, and the legacy household/case slice).
UNSECURED = {
    "organization_membership", "idempotency_key", "household", "person", "household_member",
    "assessment", "legacy_observation", "case_record", "legacy_need",
    # Pre-tenant routing lookup (phone_number_id -> org); SELECT-only for runtime roles.
    "channel_account",
}


def test_upgrade_from_empty_matches_models_and_downgrades():
    with scratch_database("csl_mig_empty") as url:
        cfg = alembic_config(url)
        command.upgrade(cfg, "head")
        command.check(cfg)  # models and migration agree (no pending autogenerate ops)
        command.downgrade(cfg, PREVIOUS)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")


def test_upgrade_from_previous_revision_keeps_legacy_data():
    with scratch_database("csl_mig_prev") as url:
        cfg = alembic_config(url)
        command.upgrade(cfg, PREVIOUS)
        eng = create_engine(url)
        org, hh, asm, case, obs, need = (str(uuid.uuid4()) for _ in range(6))
        with eng.begin() as c:
            c.execute(text("INSERT INTO organization (id, name, status) VALUES (:o, 'Legacy', 'active')"),
                      {"o": org})
            c.execute(text("INSERT INTO household (id, organization_id, reference_code) "
                           "VALUES (:h, :o, 'L-1')"), {"h": hh, "o": org})
            c.execute(text("INSERT INTO assessment (id, organization_id, household_id, source_channel,"
                           " reporting_relationship, answers_json, submitted_at) VALUES "
                           "(:a, :o, :h, 'phone', 'self', '{}', now())"),
                      {"a": asm, "o": org, "h": hh})
            c.execute(text("INSERT INTO case_record (id, organization_id, household_id, status, opened_at)"
                           " VALUES (:c, :o, :h, 'open', now())"), {"c": case, "o": org, "h": hh})
            c.execute(text("INSERT INTO observation (id, organization_id, assessment_id, service_type,"
                           " subject_scope, status, time_precision, reported_timezone, source_kind)"
                           " VALUES (:i, :o, :a, 'piped_water', 'household', 'unavailable', 'unknown',"
                           " 'America/Caracas', 'firsthand')"), {"i": obs, "o": org, "a": asm})
            c.execute(text("INSERT INTO need (id, organization_id, case_id, assessment_id, category,"
                           " urgency, urgency_reasons, status) VALUES (:i, :o, :c, :a,"
                           " 'water_delivery', 'urgent', '[]', 'requested')"),
                      {"i": need, "o": org, "c": case, "a": asm})

        command.upgrade(cfg, "head")
        with eng.connect() as c:
            assert c.execute(text("SELECT count(*) FROM legacy_need WHERE id = :i"),
                             {"i": need}).scalar_one() == 1
            assert c.execute(text("SELECT count(*) FROM legacy_observation WHERE id = :i"),
                             {"i": obs}).scalar_one() == 1
            # The new pilot tables took over the names.
            cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'need'"))}
            assert "report_id" in cols and "case_id" not in cols

        command.downgrade(cfg, PREVIOUS)
        with eng.connect() as c:
            assert c.execute(text("SELECT count(*) FROM need WHERE id = :i"),
                             {"i": need}).scalar_one() == 1
        command.upgrade(cfg, "head")
        eng.dispose()


def test_every_tenant_table_has_forced_rls(engine):
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
              FROM pg_class c
              JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'organization_id'
             WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
               AND a.attnotnull
        """)).all()
    tenant = {r[0]: (r[1], r[2]) for r in rows if r[0] not in UNSECURED}
    assert len(tenant) >= 45
    missing = [t for t, (rls, forced) in tenant.items() if not (rls and forced)]
    assert missing == []
    # Every ORM tenant table (TenantOwned) is covered.
    orm_tenant = {t.name for t in Base.metadata.sorted_tables
                  if "organization_id" in t.c and not t.c.organization_id.nullable}
    assert orm_tenant - UNSECURED - {"organization"} <= set(tenant)


def test_runtime_roles_cannot_bypass_rls(engine):
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
            "WHERE rolname LIKE 'csl\\_%'")).all()
    assert {r[0] for r in rows} >= {"csl_runtime", "csl_worker", "csl_provider", "csl_analyst",
                                    "csl_public"}
    for name, sup, bypass, login in rows:
        assert not sup and not bypass and not login, name


@pytest.mark.parametrize("table", ["area_boundary", "meeting_point", "report_location"])
def test_gist_indexes(engine, table):
    with engine.connect() as c:
        defs = c.execute(text("SELECT indexdef FROM pg_indexes WHERE tablename = :t"),
                         {"t": table}).scalars().all()
    assert any("USING gist" in d for d in defs)
