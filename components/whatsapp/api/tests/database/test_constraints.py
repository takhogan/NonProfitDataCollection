"""DB-020..024: profile trigger, append-only, units, links; DB-034 job claims;
DB-061 spatial resolution."""
from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import claim_jobs, system_transaction
from tests.database._pg import count, requires_pg

pytestmark = requires_pg

PLACEHOLDER = b"SYNTHETIC-PLACEHOLDER-NOT-ENCRYPTED:test"


def _new_report(db, org, profile, area, **extra):
    rid = str(uuid.uuid4())
    cols = {"id": rid, "organization_id": org, "privacy_profile_version_id": profile,
            "source_channel": "whatsapp", "reporting_relationship": "self", "area_id": area,
            "location_kind": "area_only", "answers_json": "{}", "status": "draft",
            "urgent_flagged": False, **extra}
    names = ", ".join(cols) + ", submitted_at"
    vals = ", ".join(f":{k}" for k in cols) + ", now()"
    db.execute(text(f"INSERT INTO report ({names}) VALUES ({vals})"), cols)
    return rid


def test_protective_profile_rejects_address(seeded, tx):
    """DB-023 accept: inserting an address on a protective-profile report fails."""
    with pytest.raises(IntegrityError, match="profile_forbids_addresses|forbids storing addresses"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            db.execute(text(
                "INSERT INTO report_location (id, organization_id, report_id, encrypted_address,"
                " precision, source) VALUES (:i, :o, :r, :a, 'street', 'reporter')"),
                {"i": str(uuid.uuid4()), "o": seeded["protective"], "r": seeded["prot_report"],
                 "a": PLACEHOLDER})


@pytest.mark.parametrize("field,value,match", [
    ("restricted_point", "SRID=4326;POINT(-66.92 10.50)", "forbids storing GPS"),
    ("encrypted_landmark", PLACEHOLDER, "forbids storing addresses"),
])
def test_protective_profile_rejects_points_and_landmarks(seeded, tx, field, value, match):
    with pytest.raises(IntegrityError, match=match):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            db.execute(text(
                f"INSERT INTO report_location (id, organization_id, report_id, {field},"
                f" precision, source) VALUES (:i, :o, :r, :v, 'street', 'reporter')"),
                {"i": str(uuid.uuid4()), "o": seeded["protective"], "r": seeded["prot_report"],
                 "v": value})


def test_protective_profile_rejects_names_and_households(seeded, tx):
    with pytest.raises(IntegrityError, match="forbids storing reporter names"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            _new_report(db, seeded["protective"], seeded["prot_profile"], seeded["prot_sector"],
                        encrypted_reporter_name=PLACEHOLDER)
    with pytest.raises(IntegrityError, match="forbids address locations"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            _new_report(db, seeded["protective"], seeded["prot_profile"], seeded["prot_sector"],
                        location_kind="address")


def test_standard_profile_allows_address_and_point(seeded, tx):
    with tx(seeded["standard"], seeded["std_coordinator"], "coordinator") as db:
        rid = _new_report(db, seeded["standard"], seeded["std_profile"], seeded["std_sector"],
                          location_kind="address", encrypted_reporter_name=PLACEHOLDER)
        db.execute(text(
            "INSERT INTO report_location (id, organization_id, report_id, encrypted_address,"
            " restricted_point, precision, source) VALUES (:i, :o, :r, :a,"
            " 'SRID=4326;POINT(-66.919 10.501)', 'street', 'reporter')"),
            {"i": str(uuid.uuid4()), "o": seeded["standard"], "r": rid, "a": PLACEHOLDER})
        db.rollback()


def test_report_profile_version_is_immutable(seeded, tx):
    with pytest.raises(IntegrityError, match="immutable"):
        with tx(seeded["standard"], seeded["std_coordinator"], "coordinator") as db:
            db.execute(text("UPDATE report SET privacy_profile_version_id = :p WHERE id = :r"),
                       {"p": str(uuid.uuid4()), "r": seeded["std_report"]})


def test_activated_profile_version_is_immutable(seeded, tx):
    with pytest.raises(IntegrityError, match="immutable"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "org_admin") as db:
            db.execute(text("UPDATE privacy_profile_version SET names_allowed = true"))
    # Disabling the public dashboard is allowed without a new version.
    with tx(seeded["standard"], seeded["std_coordinator"], "org_admin") as db:
        db.execute(text("UPDATE privacy_profile_version SET public_dashboard_enabled = false"))
        db.rollback()


@pytest.mark.parametrize("table", ["share_event", "audit_event", "export_record"])
def test_append_only_tables(seeded, tx, table):
    org = seeded["protective"]
    with tx(org, seeded["prot_coordinator"], "coordinator") as db:
        if table == "share_event":
            po, _ = seeded["prot_vetted"]
            rk = db.execute(text("SELECT id FROM reporter_key LIMIT 1")).scalar_one()
            db.execute(text("INSERT INTO share_event (id, organization_id,"
                            " provider_organization_id, actor_ref, reporter_key_id, fields_shared,"
                            " occurred_at) VALUES (:i, :o, :p, 'test', :k, '[]', now())"),
                       {"i": str(uuid.uuid4()), "o": org, "p": po, "k": rk})
        elif table == "audit_event":
            db.execute(text("INSERT INTO audit_event (id, organization_id, action, entity_type,"
                            " occurred_at, redacted_change_summary) VALUES (:i, :o, 'test',"
                            " 'report', now(), '{}')"), {"i": str(uuid.uuid4()), "o": org})
        else:
            db.execute(text("INSERT INTO export_record (id, organization_id, kind, filters_json,"
                            " row_count) VALUES (:i, :o, 'aggregate', '{}', 0)"),
                       {"i": str(uuid.uuid4()), "o": org})
    for stmt in (f"UPDATE {table} SET organization_id = organization_id",
                 f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError, match="permission denied|append-only"):
            with tx(org, seeded["prot_coordinator"], "coordinator") as db:
                db.execute(text(stmt))
        # Even the worker role cannot rewrite history.
        with pytest.raises(DBAPIError, match="permission denied|append-only"):
            with tx(org, "worker", "system") as db:
                db.execute(text(stmt))


def test_append_only_trigger_blocks_role_with_privileges(seeded, session_factory):
    """Trigger is the second layer: a non-owner role granted UPDATE is still refused."""
    s = session_factory()
    try:
        with s.begin():
            s.execute(text("GRANT UPDATE ON audit_event TO csl_worker"))
            s.execute(text("SET LOCAL ROLE csl_worker"))
            s.execute(text("SELECT set_config('app.org_id', :o, true),"
                           " set_config('app.role', 'system', true)"),
                      {"o": seeded["protective"]})
            assert count(s, "SELECT count(*) FROM audit_event") > 0
            with pytest.raises(DBAPIError, match="append-only"):
                with s.begin_nested():
                    s.execute(text("UPDATE audit_event SET action = 'x'"))
            s.rollback()
    finally:
        s.close()


@pytest.mark.parametrize("category,unit,quantity,ok", [
    ("water_drinking", "liters", 20, True),
    ("charging", "devices", 2, True),
    ("charging", "liters", 20, False),
    ("water_other", "devices", 1, False),
    ("water_drinking", None, 20, False),
    ("water_drinking", "liters", -1, False),
])
def test_need_units(seeded, tx, category, unit, quantity, ok):
    """DB-020."""
    def insert():
        with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
            nid = str(uuid.uuid4())
            db.execute(text(
                "INSERT INTO need (id, organization_id, report_id, category, quantity, unit,"
                " remaining_supply, stated_urgency, urgency_inputs, access_flags, preferred_times,"
                " status, status_changed_at, last_confirmed_at, refresh_prompt_count) VALUES"
                " (:i, :o, :r, :c, :q, :u, 'unknown', 'unknown', '{}', '{}', '[]', 'active',"
                " now(), now(), 0)"),
                {"i": nid, "o": seeded["protective"], "r": seeded["prot_report"], "c": category,
                 "q": quantity, "u": unit})
            filled = db.execute(text("SELECT area_id, reporter_key_id FROM need WHERE id = :i"),
                                {"i": nid}).one()
            assert filled[0] is not None and filled[1] is not None  # copied from report
            db.rollback()
    if ok:
        insert()
    else:
        with pytest.raises(IntegrityError, match="ck_need"):
            insert()


def test_observation_link_no_self_or_duplicate_pairs(seeded, tx):
    """DB-024."""
    with tx(seeded["protective"], seeded["prot_coordinator"], "reviewer") as db:
        a, b = sorted(db.execute(text("SELECT id FROM observation LIMIT 2")).scalars().all())
    with pytest.raises(IntegrityError, match="ck_observation_link_order"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "reviewer") as db:
            db.execute(text("INSERT INTO observation_link (id, organization_id, observation_a_id,"
                            " observation_b_id, relation, rule_version, reasons_json) VALUES"
                            " (:i, :o, :b, :a, 'conflicts_with', 'v1', '[]')"),
                       {"i": str(uuid.uuid4()), "o": seeded["protective"], "a": a, "b": b})
    with pytest.raises(IntegrityError, match="ck_review_task_target"):
        with tx(seeded["protective"], seeded["prot_coordinator"], "reviewer") as db:
            db.execute(text("INSERT INTO review_task (id, organization_id, reason, status,"
                            " reasons_json) VALUES (:i, :o, 'outlier_cell', 'open', '[]')"),
                       {"i": str(uuid.uuid4()), "o": seeded["protective"]})


def test_resolve_area_for_point(seeded, tx):
    """DB-061: point-in-area returns the sector, scoped to the tenant."""
    with tx(seeded["protective"], seeded["prot_coordinator"], "coordinator") as db:
        sector = db.execute(text(
            "SELECT a.id FROM area a JOIN area_boundary b ON b.area_id = a.id "
            "WHERE a.type = 'sector' AND a.official_code = 'DC-LIB-CAT-S1'")).scalar_one()
        got = db.execute(text(
            "SELECT resolve_area_for_point(ST_GeomFromText('POINT(-66.9185 10.5015)'))")
        ).scalar_one()
        assert got == sector
        assert db.execute(text(
            "SELECT resolve_area_for_point(ST_GeomFromText('POINT(0 0)'))")).scalar_one() is None
    with tx(seeded["standard"], seeded["std_coordinator"], "coordinator") as db:
        other = db.execute(text(
            "SELECT resolve_area_for_point(ST_GeomFromText('POINT(-66.9185 10.5015)'))")
        ).scalar_one()
        assert other != sector  # same geography, but the standard org's own area row


def test_claim_jobs_skip_locked(seeded, session_factory):
    """DB-034: two concurrent workers never claim the same job."""
    marker = f"test-{uuid.uuid4().hex[:6]}"
    with system_transaction(session=session_factory()) as db:
        for i in range(10):
            db.execute(text("INSERT INTO job (id, kind, payload_json, status, priority, attempts,"
                            " max_attempts, run_after) VALUES (:i, :k, '{}', 'queued', 100, 0, 5,"
                            " now())"), {"i": str(uuid.uuid4()), "k": marker})
    claimed: dict[str, list[str]] = {}
    barrier = threading.Barrier(2)

    def worker(name):
        s = session_factory()
        try:
            with system_transaction(name, session=s) as db:
                rows = claim_jobs(db, name, kinds=[marker], limit=6)
                barrier.wait(timeout=10)  # hold row locks until both have claimed
                claimed[name] = [r["id"] for r in rows]
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("w1", "w2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert set(claimed["w1"]).isdisjoint(claimed["w2"])
    assert len(claimed["w1"]) + len(claimed["w2"]) == 10
    with system_transaction(session=session_factory()) as db:
        assert count(db, "SELECT count(*) FROM job WHERE kind = :k AND status = 'running'",
                     k=marker) == 10
        # Job tables grant no tenant data.
        assert count(db, "SELECT count(*) FROM report") == 0
