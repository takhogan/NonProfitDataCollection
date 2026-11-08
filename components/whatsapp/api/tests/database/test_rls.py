"""DB-002/003/005: tenant isolation and role-aware access via row-level security.

All sessions connect as the owner/superuser login of the test server; the
tenant helper's SET LOCAL ROLE is what makes RLS apply, exactly as in
production for a login that is a member of the csl_* group roles.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.db import lookup_api_key
from tests.database._pg import count, requires_pg
from tests.database.test_migrations import UNSECURED

pytestmark = requires_pg


def _tenant_tables(db):
    rows = db.execute(text("""
        SELECT c.relname FROM pg_class c
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'organization_id'
         WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace AND a.attnotnull
         ORDER BY 1""")).scalars().all()
    return [t for t in rows if t not in UNSECURED]


def test_seed_shape(seeded, tx):
    """DB-090: about 300 reports across both orgs, mixed scenarios."""
    for org, coord in ((seeded["protective"], seeded["prot_coordinator"]),
                       (seeded["standard"], seeded["std_coordinator"])):
        with tx(org, coord, "coordinator") as db:
            assert count(db, "SELECT count(*) FROM report") == 150
            # repeat reporters
            assert count(db, "SELECT count(*) FROM (SELECT reporter_key_id FROM report "
                             "WHERE reporter_key_id IS NOT NULL GROUP BY 1 HAVING count(*) >= 3) x") >= 10
            # unknown-coverage sectors: sectors with no reports
            assert count(db, "SELECT count(*) FROM area a WHERE a.type = 'sector' AND NOT EXISTS "
                             "(SELECT 1 FROM report r WHERE r.area_id = a.id)") == 2
            # outage spike: >= 30 electricity-unavailable observations in one sector in 6h
            assert count(db, "SELECT max(n) FROM (SELECT count(*) n FROM observation "
                             "WHERE service_type = 'electricity' AND status = 'unavailable' "
                             "AND observed_at > now() - interval '7 hours' GROUP BY area_id) x") >= 30
            # mixed permissions
            assert count(db, "SELECT count(DISTINCT decision) FROM permission "
                             "WHERE purpose = 'contact_list'") == 2
            assert count(db, "SELECT count(*) FROM provider_organization") == 3
    with tx(seeded["standard"], seeded["std_coordinator"], "coordinator") as db:
        # shared phones: one reporter key speaking for several households
        assert count(db, "SELECT count(*) FROM (SELECT reporter_key_id FROM report "
                         "WHERE household_id IS NOT NULL GROUP BY 1 "
                         "HAVING count(DISTINCT household_id) > 1) x") >= 1


def test_no_tenant_means_no_rows(seeded, tx):
    with tx(None, "worker", "system") as db:
        for t in _tenant_tables(db):
            assert count(db, f"SELECT count(*) FROM {t}") == 0, t


def test_cross_tenant_isolation_every_table(seeded, tx):
    """DB-005: each tenant sees zero rows of the other tenant in every tenant table."""
    pairs = [(seeded["protective"], seeded["standard"], seeded["prot_coordinator"]),
             (seeded["standard"], seeded["protective"], seeded["std_coordinator"])]
    for mine, other, actor in pairs:
        with tx(mine, actor, "system") as db:
            tables = _tenant_tables(db)
            seen_own = 0
            for t in tables:
                assert count(db, f"SELECT count(*) FROM {t} WHERE organization_id = :o",
                             o=other) == 0, t
                assert count(db, f"SELECT count(*) FROM {t} WHERE organization_id <> :o",
                             o=mine) == 0, t
                seen_own += count(db, f"SELECT count(*) FROM {t}")
            assert seen_own > 0
            # Views filter the tenant too.
            for v in ("v_indicator_cell", "v_coverage_cell", "v_activity"):
                assert count(db, f"SELECT count(*) FROM {v} WHERE organization_id = :o",
                             o=other) == 0


def test_cannot_write_into_another_tenant(seeded, tx):
    with pytest.raises(ProgrammingError, match="row-level security"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            db.execute(text(
                "INSERT INTO meeting_point (id, organization_id, area_id, name, kind, status,"
                " lock_version) VALUES (:i, :o, :a, 'x', 'plaza', 'active', 1)"),
                {"i": str(uuid.uuid4()), "o": seeded["standard"], "a": seeded["std_sector"]})


def test_cannot_update_rows_of_another_tenant(seeded, tx):
    with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
        res = db.execute(text("UPDATE area SET name = 'hijacked' WHERE organization_id = :o"),
                         {"o": seeded["standard"]})
        assert res.rowcount == 0


def test_org_scoped_composite_fk(seeded, tx):
    """DB-001: a report cannot reference another org's area even if RLS let it see it."""
    with pytest.raises(IntegrityError, match="fk_report_area_id"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            db.execute(text(
                "INSERT INTO report (id, organization_id, privacy_profile_version_id,"
                " source_channel, reporting_relationship, area_id, location_kind, answers_json,"
                " status, submitted_at, urgent_flagged) VALUES (:i, :o, :p, 'phone', 'area', :a,"
                " 'area_only', '{}', 'draft', now(), false)"),
                {"i": str(uuid.uuid4()), "o": seeded["protective"], "p": seeded["prot_profile"],
                 "a": seeded["std_sector"]})


@pytest.mark.parametrize("table", ["report", "contact_endpoint", "permission", "review_task",
                                   "review_decision", "need", "reporter_key", "indicator_cell"])
def test_provider_session_cannot_select_sensitive_tables(seeded, tx, table):
    """DB-003 accept: a provider session cannot select from report, contact_endpoint,
    permission, or review_* (nor raw needs, reporter keys, or unsuppressed cells)."""
    po, member = seeded["prot_vetted"]
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tx(seeded["protective"], member, "provider", provider_org_id=po) as db:
            db.execute(text(f"SELECT * FROM {table} LIMIT 1")).all()


def test_provider_app_role_on_runtime_db_role_sees_nothing_sensitive(seeded, session_factory):
    """Defense in depth: even if a provider request ran on the staff DB role, the
    restrictive staff_only policy returns no rows."""
    s = session_factory()
    try:
        with s.begin():
            s.execute(text("SET LOCAL ROLE csl_runtime"))
            s.execute(text("SELECT set_config('app.org_id', :o, true),"
                           " set_config('app.role', 'provider', true)"),
                      {"o": seeded["protective"]})
            for t in ("report", "contact_endpoint", "permission", "need", "review_task"):
                assert count(s, f"SELECT count(*) FROM {t}") == 0, t
            assert count(s, "SELECT count(*) FROM area") > 0
    finally:
        s.close()


def test_provider_reads_views_and_own_rows(seeded, tx):
    po, member = seeded["prot_vetted"]
    with tx(seeded["protective"], member, "provider", provider_org_id=po) as db:
        assert count(db, "SELECT count(*) FROM v_activity") == 6  # all providers' activities
        hidden = db.execute(text(
            "SELECT provider_name, schedule_json FROM v_activity WHERE details_hidden")).all()
        assert hidden and all(r == (None, None) for r in hidden)
        assert count(db, "SELECT count(*) FROM activity") == 2  # own only
        assert count(db, "SELECT count(*) FROM provider_organization") == 1
        assert count(db, "SELECT count(*) FROM alert_subscription") == 1


def test_contact_list_vetted_only_and_consent_bound(seeded, tx):
    """DOM-054 in SQL."""
    po, member = seeded["prot_vetted"]
    with tx(seeded["protective"], member, "provider", provider_org_id=po) as db:
        rows = db.execute(text("SELECT * FROM provider_contact_list")).mappings().all()
        assert rows, "seed should give the vetted water provider some opted-in reporters"
        assert all(r["provider_organization_id"] == po for r in rows)
        assert all(r["category"] in ("water_drinking", "water_other") for r in rows)
        # protective fields: alias/sector/meeting point/phone, never name/address
        assert all(r["encrypted_name"] is None and r["encrypted_address"] is None for r in rows)
        assert all(r["alias"] and r["encrypted_phone"] for r in rows)
        keys = {r["reporter_key_id"] for r in rows}
    with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
        for k in keys:
            assert count(db, "SELECT count(*) FROM permission WHERE reporter_key_id = :k AND "
                             "purpose = 'contact_list' AND decision = 'granted' AND "
                             "withdrawn_at IS NULL", k=k) == 1
        assert count(db, "SELECT count(*) FROM need WHERE reporter_key_id = ANY(:k) "
                         "AND status = 'active'", k=list(keys)) >= len(keys)
    upo, umember = seeded["prot_unvetted"]
    with tx(seeded["protective"], umember, "provider", provider_org_id=upo) as db:
        assert count(db, "SELECT count(*) FROM provider_contact_list") == 0
    # A provider cannot widen its view by claiming another provider org id in app context:
    with tx(seeded["protective"], umember, "provider", provider_org_id=upo) as db:
        assert count(db, "SELECT count(*) FROM provider_contact_list "
                         "WHERE provider_organization_id = :p", p=po) == 0


def test_standard_contact_list_fields(seeded, tx):
    po, member = seeded["std_vetted"]
    with tx(seeded["standard"], member, "provider", provider_org_id=po) as db:
        rows = db.execute(text("SELECT * FROM provider_contact_list")).mappings().all()
        assert rows
        assert all(r["alias"] is None and r["meeting_point_id"] is None for r in rows)
        assert any(r["encrypted_address"] is not None for r in rows)


def test_analyst_reads_aggregates_only(seeded, tx):
    with tx(seeded["protective"], seeded["prot_coordinator"], "analyst") as db:
        assert count(db, "SELECT count(*) FROM v_indicator_cell") == 0
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "analyst") as db:
            db.execute(text("SELECT * FROM report LIMIT 1")).all()


@pytest.mark.parametrize("table", ["area", "indicator_cell", "activity", "report"])
def test_public_reads_only_public_tables(seeded, tx, table):
    with tx(seeded["standard"], None, "public") as db:
        assert count(db, "SELECT count(*) FROM public_indicator_cell") == 0
    with pytest.raises(ProgrammingError, match="permission denied"):
        with tx(seeded["standard"], None, "public") as db:
            db.execute(text(f"SELECT 1 FROM {table} LIMIT 1")).all()


def test_volunteer_sees_only_own_recent_reports(seeded, tx):
    vol = seeded["prot_volunteer"]
    with tx(seeded["protective"], vol, "intake_volunteer") as db:
        n = count(db, "SELECT count(*) FROM report")
        assert n == count(db, "SELECT count(*) FROM report WHERE entered_by_membership_id = :v "
                              "AND submitted_at > now() - interval '72 hours'", v=vol)
        assert n < 150


def test_context_is_transaction_local(seeded, session_factory, tx):
    s = session_factory()
    try:
        from app.db import tenant_transaction

        with tenant_transaction(seeded["protective"], "x", "coordinator", session=s):
            pass
        with s.begin():
            assert s.execute(text("SELECT coalesce(current_setting('app.org_id', true), '')")
                             ).scalar_one() == ""
            assert s.execute(text("SELECT current_user")).scalar_one() != "csl_runtime"
    finally:
        s.close()


def test_api_key_lookup_before_tenant(seeded, session_factory, engine):
    with engine.connect() as c:
        h = c.execute(text("SELECT key_hash FROM api_key WHERE organization_id = :o LIMIT 1"),
                      {"o": seeded["protective"]}).scalar_one()
    s = session_factory()
    try:
        found = lookup_api_key(h, session=s)
        assert found and found["organization_id"] == seeded["protective"]
        assert lookup_api_key("not-a-key", session=s) is None
    finally:
        s.close()


def test_raw_role_without_helper_cannot_escalate(seeded, session_factory):
    """A runtime DB role cannot turn RLS off or read other tenants by itself."""
    s = session_factory()
    try:
        with pytest.raises(DBAPIError):
            with s.begin():
                s.execute(text("SET LOCAL ROLE csl_runtime"))
                s.execute(text("ALTER TABLE report DISABLE ROW LEVEL SECURITY"))
    finally:
        s.close()
