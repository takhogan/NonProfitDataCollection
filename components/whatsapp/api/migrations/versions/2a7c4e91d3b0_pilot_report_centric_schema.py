"""pilot report-centric schema (DB-001..005, DB-010..014, DB-022/023, DB-061)

Revision ID: 2a7c4e91d3b0
Revises: 1eb5e1be9f8b
Create Date: 2026-11-07 19:41:57.220783
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2a7c4e91d3b0'
down_revision: Union[str, None] = '1eb5e1be9f8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# What this migration does (DB-001..005, DB-022/023, DB-061, DB-091)
#
# 1. Renames the legacy household/case `observation` and `need` tables to
#    `legacy_observation` / `legacy_need` (no data dropped). The API still uses
#    them until the api session migrates to the report-centric model.
# 2. Creates the pilot tables with org-scoped composite foreign keys.
# 3. PostgreSQL only (raw SQL via op.execute):
#    - group roles csl_runtime / csl_worker / csl_provider / csl_analyst /
#      csl_public (NOLOGIN, NOBYPASSRLS) and their grants (DB-004)
#    - RLS enabled + FORCED on every pilot tenant table; tenant comes from the
#      transaction-local setting app.org_id (DB-002); role-aware restrictive
#      policies (DB-003)
#    - profile-constraint triggers (DB-023), append-only triggers (DB-022),
#      denormalization triggers, profile-version immutability
#    - suppressing read views for providers/analysts (DB-076) and the
#      provider_contact_list view (DOM-054)
#    - GiST indexes and point-in-area resolution (DB-061)
#
# Role guidance (see README "Database (pilot schema)"):
#  - The *migration* login owns all tables and runs only `alembic upgrade`.
#    It needs CREATEROLE (to create the csl_* group roles) and must be able to
#    CREATE EXTENSION postgis.
#  - Runtime logins (API, worker) must NOT own tables and must NOT have
#    BYPASSRLS. Grant them membership in the group roles they may switch to:
#      GRANT csl_runtime, csl_provider, csl_analyst, csl_public TO api_login;
#      GRANT csl_worker TO worker_login;
#    app.db.tenant_transaction() runs SET LOCAL ROLE <group role> per request.
#  - Backups use a separate role with pg_read_all_data (outside this migration).
# ---------------------------------------------------------------------------

RUNTIME_ROLES = ("csl_runtime", "csl_worker", "csl_provider", "csl_analyst", "csl_public")
STAFF_ROLE_SQL = "('org_admin', 'coordinator', 'reviewer', 'intake_volunteer', 'system')"

# Pilot tenant tables: non-null organization_id, RLS enabled and forced.
TENANT_TABLES = (
    "privacy_profile_version", "policy_version",
    "area", "area_alias", "area_boundary", "meeting_point", "outage_episode",
    "questionnaire_version", "campaign", "campaign_area",
    "contact_endpoint", "reporter_key", "permission", "conversation", "message",
    "report", "report_location", "observation", "need",
    "water_need_detail", "charging_need_detail", "charging_device_request",
    "provider_organization", "provider_scope", "activity", "activity_area",
    "alert_subscription", "alert_subscription_area", "alert_delivery", "api_key",
    "export_record", "share_event", "broadcast", "broadcast_delivery",
    "indicator_cell", "coverage_cell", "indicator_dirty_cell", "external_indicator",
    "public_indicator_cell", "public_activity",
    "observation_link", "duplicate_candidate", "review_task", "review_decision",
    "merge_event", "data_job", "data_job_result", "outbox_message", "audit_event",
)
# Person-level or review data: staff roles only (restrictive policy).
SENSITIVE_TABLES = (
    "report", "report_location", "observation", "need", "water_need_detail",
    "charging_need_detail", "charging_device_request", "contact_endpoint", "reporter_key",
    "permission", "conversation", "message", "outbox_message", "review_task",
    "review_decision", "duplicate_candidate", "merge_event", "observation_link",
    "audit_event",
)
APPEND_ONLY_TABLES = (
    "share_event", "export_record", "alert_delivery", "audit_event", "review_decision",
    "merge_event",
)
# Derived: written only by the worker (DB-075/077).
DERIVED_TABLES = ("indicator_cell", "coverage_cell", "public_indicator_cell", "public_activity")
# Not row-level-secured yet: identity tables (login runs before tenant context)
# and the legacy household/case slice still used by the hackathon API.
UNSECURED_APP_TABLES = (
    "organization", '"user"', "organization_membership", "idempotency_key",
    "household", "person", "household_member", "assessment", "legacy_observation",
    "case_record", "legacy_need",
)
QUEUE_TABLES = ("job", "inbound_event", "message_status_event")
VIEWS = ("v_indicator_cell", "v_coverage_cell", "v_activity", "provider_contact_list")

LEGACY_RENAMES = {
    "observation": ("assessment_id", "household_id", "organization_id"),
    "need": ("assessment_id", "case_id", "organization_id"),
}


def _geom(kind: str, pg: bool):
    if pg:
        from geoalchemy2 import Geometry

        return Geometry(kind, srid=4326, spatial_index=False)
    return sa.Text()


def _rename_legacy_tables(pg: bool) -> None:
    for old, cols in LEGACY_RENAMES.items():
        new = f"legacy_{old}"
        op.rename_table(old, new)
        if pg:
            op.execute(f"ALTER INDEX {old}_pkey RENAME TO {new}_pkey")
            for c in cols:
                op.execute(f"ALTER INDEX ix_{old}_{c} RENAME TO ix_{new}_{c}")
        else:
            for c in cols:
                op.drop_index(f"ix_{old}_{c}", table_name=new)
                op.create_index(f"ix_{new}_{c}", new, [c])


def _restore_legacy_tables(pg: bool) -> None:
    for old, cols in LEGACY_RENAMES.items():
        new = f"legacy_{old}"
        op.rename_table(new, old)
        if pg:
            op.execute(f"ALTER INDEX {new}_pkey RENAME TO {old}_pkey")
            for c in cols:
                op.execute(f"ALTER INDEX ix_{new}_{c} RENAME TO ix_{old}_{c}")
        else:
            for c in cols:
                op.drop_index(f"ix_{new}_{c}", table_name=old)
                op.create_index(f"ix_{old}_{c}", old, [c])


def _grant(privs: str, tables, roles) -> None:
    op.execute(f"GRANT {privs} ON {', '.join(tables)} TO {', '.join(roles)}")


FUNCTIONS_SQL = r"""
-- Transaction-local context (set by app.db.tenant_transaction with set_config(..., true)).
CREATE OR REPLACE FUNCTION app_current_org() RETURNS text
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.org_id', true), '') $$;
CREATE OR REPLACE FUNCTION app_current_actor() RETURNS text
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.actor_id', true), '') $$;
CREATE OR REPLACE FUNCTION app_current_role() RETURNS text
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.role', true), '') $$;
CREATE OR REPLACE FUNCTION app_current_provider_org() RETURNS text
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.provider_org_id', true), '') $$;

-- DB-023: names / households / address mode must match the report's profile version.
CREATE OR REPLACE FUNCTION app_enforce_report_profile() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE p record;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.privacy_profile_version_id IS DISTINCT FROM OLD.privacy_profile_version_id THEN
    RAISE EXCEPTION 'report.privacy_profile_version_id is immutable'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_version_immutable';
  END IF;
  SELECT names_allowed, household_records_allowed, location_mode INTO p
    FROM privacy_profile_version
   WHERE id = NEW.privacy_profile_version_id AND organization_id = NEW.organization_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'report references an unknown privacy profile version'
      USING ERRCODE = '23503', CONSTRAINT = 'profile_version_missing';
  END IF;
  IF NOT p.names_allowed AND NEW.encrypted_reporter_name IS NOT NULL THEN
    RAISE EXCEPTION 'privacy profile forbids storing reporter names'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_forbids_names';
  END IF;
  IF NOT p.household_records_allowed AND NEW.household_id IS NOT NULL THEN
    RAISE EXCEPTION 'privacy profile forbids household records'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_forbids_households';
  END IF;
  IF p.location_mode <> 'address' AND NEW.location_kind = 'address' THEN
    RAISE EXCEPTION 'privacy profile forbids address locations'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_forbids_addresses';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION app_enforce_report_location_profile() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE p record;
BEGIN
  SELECT v.location_mode, v.gps_allowed INTO p
    FROM report r
    JOIN privacy_profile_version v
      ON v.id = r.privacy_profile_version_id AND v.organization_id = r.organization_id
   WHERE r.id = NEW.report_id AND r.organization_id = NEW.organization_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'report_location references an unknown report'
      USING ERRCODE = '23503', CONSTRAINT = 'profile_version_missing';
  END IF;
  IF p.location_mode <> 'address'
     AND (NEW.encrypted_address IS NOT NULL OR NEW.encrypted_landmark IS NOT NULL) THEN
    RAISE EXCEPTION 'privacy profile forbids storing addresses or landmarks'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_forbids_addresses';
  END IF;
  IF NOT p.gps_allowed AND NEW.restricted_point IS NOT NULL THEN
    RAISE EXCEPTION 'privacy profile forbids storing GPS points'
      USING ERRCODE = '23514', CONSTRAINT = 'profile_forbids_points';
  END IF;
  RETURN NEW;
END $$;

-- Activated profile versions are immutable; a change is a new version.
-- Only status active -> retired and public_dashboard_enabled true -> false are allowed.
CREATE OR REPLACE FUNCTION app_profile_version_guard() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'draft' THEN
    RETURN NEW;
  END IF;
  IF (NEW.organization_id, NEW.version, NEW.profile_key, NEW.names_allowed, NEW.location_mode,
      NEW.gps_allowed, NEW.household_records_allowed, NEW.contact_list_allowed,
      NEW.contact_list_fields, NEW.reporter_phone_retention_days, NEW.reporter_key_rotation_days,
      NEW.report_retention_days, NEW.aggregate_k, NEW.public_level, NEW.public_k,
      NEW.public_delay_hours, NEW.settings_json, NEW.notice_version, NEW.activated_at,
      NEW.activated_by_membership_id)
     IS DISTINCT FROM
     (OLD.organization_id, OLD.version, OLD.profile_key, OLD.names_allowed, OLD.location_mode,
      OLD.gps_allowed, OLD.household_records_allowed, OLD.contact_list_allowed,
      OLD.contact_list_fields, OLD.reporter_phone_retention_days, OLD.reporter_key_rotation_days,
      OLD.report_retention_days, OLD.aggregate_k, OLD.public_level, OLD.public_k,
      OLD.public_delay_hours, OLD.settings_json, OLD.notice_version, OLD.activated_at,
      OLD.activated_by_membership_id)
     OR (NEW.public_dashboard_enabled AND NOT OLD.public_dashboard_enabled)
     OR (OLD.status = 'retired' AND NEW.status <> 'retired')
     OR (OLD.status = 'active' AND NEW.status NOT IN ('active', 'retired')) THEN
    RAISE EXCEPTION 'activated privacy profile version % is immutable', OLD.version
      USING ERRCODE = '23514', CONSTRAINT = 'profile_version_immutable';
  END IF;
  RETURN NEW;
END $$;

-- DB-022/DB-053: append-only for every role except the table owner
-- (migration / retention role).
CREATE OR REPLACE FUNCTION app_forbid_mutation() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  IF pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = TG_RELID), 'USAGE') THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '42501';
END $$;

-- need/observation carry area_id (and reporter_key_id) copied from the report,
-- so aggregates and the contact list never read the report table.
CREATE OR REPLACE FUNCTION app_fill_from_report() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE r record;
BEGIN
  SELECT area_id, reporter_key_id INTO r FROM report
   WHERE id = NEW.report_id AND organization_id = NEW.organization_id;
  IF FOUND THEN
    NEW.area_id := coalesce(NEW.area_id, r.area_id);
    IF TG_TABLE_NAME = 'need' THEN
      NEW.reporter_key_id := coalesce(NEW.reporter_key_id, r.reporter_key_id);
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- Public snapshots are visible only while the tenant's active profile enables
-- the dashboard. Definer so the public role needs no access to profiles.
CREATE OR REPLACE FUNCTION app_public_dashboard_enabled(org text) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM privacy_profile_version p
                  WHERE p.organization_id = org AND p.status = 'active'
                    AND p.public_dashboard_enabled)
$$;

-- DB-061 point-in-area: smallest current area of the tenant containing p.
CREATE OR REPLACE FUNCTION resolve_area_for_point(p geometry) RETURNS text
  LANGUAGE sql STABLE AS $$
  SELECT b.area_id
    FROM area_boundary b
    JOIN area a ON a.id = b.area_id AND a.organization_id = b.organization_id
   WHERE b.organization_id = app_current_org()
     AND b.valid_to IS NULL
     AND ST_Covers(b.boundary, ST_SetSRID(p, 4326))
   ORDER BY CASE a.type WHEN 'sector' THEN 0 WHEN 'parish' THEN 1
                        WHEN 'municipality' THEN 2 ELSE 3 END
   LIMIT 1
$$;
"""

TRIGGERS_SQL = """
CREATE TRIGGER trg_report_profile BEFORE INSERT OR UPDATE ON report
  FOR EACH ROW EXECUTE FUNCTION app_enforce_report_profile();
CREATE TRIGGER trg_report_location_profile BEFORE INSERT OR UPDATE ON report_location
  FOR EACH ROW EXECUTE FUNCTION app_enforce_report_location_profile();
CREATE TRIGGER trg_privacy_profile_version_guard BEFORE UPDATE ON privacy_profile_version
  FOR EACH ROW EXECUTE FUNCTION app_profile_version_guard();
CREATE TRIGGER trg_need_fill BEFORE INSERT ON need
  FOR EACH ROW EXECUTE FUNCTION app_fill_from_report();
CREATE TRIGGER trg_observation_fill BEFORE INSERT ON observation
  FOR EACH ROW EXECUTE FUNCTION app_fill_from_report();
"""

VIEWS_SQL = """
-- DB-076: suppression in SQL. Counts are NULL when the cell is suppressed by the
-- worker or has fewer distinct reporters than the cell's profile k (min 3).
-- Views run with the owner's rights, so each filters the tenant explicitly
-- (the owner may be a superuser in development, which bypasses RLS).
CREATE VIEW v_indicator_cell WITH (security_barrier) AS
SELECT c.id, c.organization_id, c.area_id, c.level, c.subject, c.bucket, c.bucket_start,
       x.suppressed,
       CASE WHEN x.suppressed THEN NULL ELSE c.active_needs END AS active_needs,
       CASE WHEN x.suppressed THEN NULL ELSE c.distinct_reporters END AS distinct_reporters,
       CASE WHEN x.suppressed THEN NULL ELSE c.distinct_households END AS distinct_households,
       CASE WHEN x.suppressed THEN NULL ELSE c.people_known END AS people_known,
       CASE WHEN x.suppressed THEN NULL ELSE c.people_unknown_count END AS people_unknown_count,
       CASE WHEN x.suppressed THEN NULL ELSE c.urgency_mix END AS urgency_mix,
       CASE WHEN x.suppressed THEN NULL ELSE c.supply_mix END AS supply_mix,
       CASE WHEN x.suppressed THEN NULL ELSE c.status_mix END AS status_mix,
       CASE WHEN x.suppressed THEN NULL ELSE c.pending_review_share END AS pending_review_share,
       c.freshness_at, c.coverage_label, c.confidence_label, c.confidence_reasons,
       c.method_version, c.profile_version_id, c.input_watermark, c.computed_at
  FROM indicator_cell c
  JOIN privacy_profile_version p
    ON p.id = c.profile_version_id AND p.organization_id = c.organization_id
  CROSS JOIN LATERAL (
    SELECT (c.suppressed OR c.distinct_reporters < greatest(p.aggregate_k, 3)) AS suppressed
  ) x
 WHERE c.organization_id = app_current_org();

CREATE VIEW v_coverage_cell WITH (security_barrier) AS
SELECT c.id, c.organization_id, c.area_id, c.category, c.coverage, c.activity_ids,
       c.method_version, c.computed_at
  FROM coverage_cell c
 WHERE c.organization_id = app_current_org();

-- DOM-053: internal-only activities count for coverage but hide their details
-- from other providers. DOM-051: unconfirmed after 7 days.
CREATE VIEW v_activity WITH (security_barrier) AS
SELECT a.id, a.organization_id, a.provider_organization_id,
       CASE WHEN x.hide THEN NULL ELSE po.name END AS provider_name,
       a.type, a.category, a.status, a.visibility, x.hide AS details_hidden,
       CASE WHEN x.hide THEN NULL ELSE a.schedule_json END AS schedule_json,
       CASE WHEN x.hide THEN NULL ELSE a.starts_at END AS starts_at,
       CASE WHEN x.hide THEN NULL ELSE a.ends_at END AS ends_at,
       CASE WHEN x.hide THEN NULL ELSE a.capacity END AS capacity,
       CASE WHEN x.hide THEN NULL ELSE a.capacity_unit END AS capacity_unit,
       CASE WHEN x.hide THEN NULL ELSE a.public_meeting_point_id END AS public_meeting_point_id,
       CASE WHEN x.hide THEN NULL ELSE a.public_location_description END
         AS public_location_description,
       a.last_confirmed_at,
       (a.last_confirmed_at < now() - interval '7 days') AS unconfirmed,
       ARRAY(SELECT aa.area_id FROM activity_area aa
              WHERE aa.activity_id = a.id AND aa.organization_id = a.organization_id
              ORDER BY aa.area_id) AS area_ids
  FROM activity a
  JOIN provider_organization po
    ON po.id = a.provider_organization_id AND po.organization_id = a.organization_id
  CROSS JOIN LATERAL (
    SELECT (a.visibility = 'internal'
            AND a.provider_organization_id IS DISTINCT FROM app_current_provider_org()
            AND coalesce(app_current_role(), '') NOT IN ('org_admin', 'coordinator', 'system'))
           AS hide
  ) x
 WHERE a.organization_id = app_current_org();

-- DOM-054: a vetted provider sees a reporter only with list consent, an active
-- need in its scope (scope area = the need's sector or its parent), and a
-- profile that allows contact lists. Fields follow the active profile's
-- contact_list_fields. One row per (reporter, active need). Reading or
-- exporting it must write share_event rows in the same transaction (DB-033).
CREATE VIEW provider_contact_list WITH (security_barrier) AS
SELECT po.id AS provider_organization_id, po.organization_id,
       rk.id AS reporter_key_id,
       CASE WHEN ap.contact_list_fields ? 'alias' THEN rk.alias END AS alias,
       n.id AS need_id, n.category, n.stated_urgency, n.remaining_supply, n.people_affected,
       n.last_confirmed_at, n.area_id,
       CASE WHEN ap.contact_list_fields ? 'sector' THEN na.name END AS sector_name,
       CASE WHEN ap.contact_list_fields ? 'meeting_point' THEN r.meeting_point_id END
         AS meeting_point_id,
       CASE WHEN ap.contact_list_fields ? 'meeting_point' THEN mp.name END AS meeting_point_name,
       CASE WHEN ap.contact_list_fields ? 'phone' THEN ce.encrypted_address END AS encrypted_phone,
       ce.key_version AS phone_key_version,
       CASE WHEN ap.contact_list_fields ? 'name' AND rp.names_allowed
            THEN r.encrypted_reporter_name END AS encrypted_name,
       CASE WHEN ap.contact_list_fields ? 'address' AND rp.location_mode = 'address'
            THEN rl.encrypted_address END AS encrypted_address
  FROM provider_organization po
  JOIN privacy_profile_version ap
    ON ap.organization_id = po.organization_id AND ap.status = 'active'
       AND ap.contact_list_allowed
  JOIN provider_scope ps
    ON ps.organization_id = po.organization_id AND ps.provider_organization_id = po.id
  JOIN need n
    ON n.organization_id = po.organization_id AND n.category = ps.category
       AND n.status = 'active'
  JOIN area na ON na.organization_id = n.organization_id AND na.id = n.area_id
  JOIN report r
    ON r.organization_id = n.organization_id AND r.id = n.report_id
       AND r.status = 'confirmed' AND r.excluded_reason IS NULL
  JOIN privacy_profile_version rp
    ON rp.organization_id = r.organization_id AND rp.id = r.privacy_profile_version_id
  JOIN reporter_key rk ON rk.organization_id = n.organization_id AND rk.id = n.reporter_key_id
  JOIN contact_endpoint ce
    ON ce.organization_id = rk.organization_id AND ce.id = rk.contact_endpoint_id
       AND ce.status = 'active'
  LEFT JOIN meeting_point mp ON mp.organization_id = r.organization_id AND mp.id = r.meeting_point_id
  LEFT JOIN report_location rl ON rl.organization_id = r.organization_id AND rl.report_id = r.id
 WHERE po.organization_id = app_current_org()
   AND po.id = app_current_provider_org()
   AND app_current_role() = 'provider'
   AND po.vetting_status = 'vetted'
   AND (ps.area_id = n.area_id OR ps.area_id = na.parent_area_id)
   AND EXISTS (
     SELECT 1 FROM permission pm
      WHERE pm.organization_id = rk.organization_id AND pm.reporter_key_id = rk.id
        AND pm.purpose = 'contact_list' AND pm.decision = 'granted'
        AND pm.withdrawn_at IS NULL AND (pm.expires_at IS NULL OR pm.expires_at > now()));
"""


def _install_postgres_objects() -> None:
    # --- roles (DB-004) ---
    op.execute(
        """
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['%s'] LOOP
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('CREATE ROLE %%I NOLOGIN NOSUPERUSER NOBYPASSRLS', r);
            END IF;
          END LOOP;
        END $$;
        """ % "', '".join(RUNTIME_ROLES)
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {', '.join(RUNTIME_ROLES)}")

    op.execute(FUNCTIONS_SQL)

    # --- GiST spatial indexes (DB-061) ---
    op.execute("CREATE INDEX ix_area_boundary_geom ON area_boundary USING gist (boundary)")
    op.execute("CREATE INDEX ix_meeting_point_geom ON meeting_point USING gist (public_point)")
    op.execute(
        "CREATE INDEX ix_report_location_geom ON report_location USING gist (restricted_point)"
    )

    # --- RLS: tenant isolation on every pilot tenant table (DB-002) ---
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (organization_id = app_current_org()) "
            f"WITH CHECK (organization_id = app_current_org())"
        )

    # --- role-aware restrictive policies (DB-003) ---
    staff = f"(app_current_role() IN {STAFF_ROLE_SQL})"
    for t in SENSITIVE_TABLES:
        op.execute(
            f"CREATE POLICY staff_only ON {t} AS RESTRICTIVE TO csl_runtime, csl_worker "
            f"USING {staff} WITH CHECK {staff}"
        )
    # Volunteers see only reports they entered, for 72 hours.
    volunteer = (
        "(coalesce(app_current_role(), '') <> 'intake_volunteer' OR "
        "(entered_by_membership_id = app_current_actor() "
        "AND submitted_at > now() - interval '72 hours'))"
    )
    op.execute(
        f"CREATE POLICY volunteer_own_recent ON report AS RESTRICTIVE TO csl_runtime "
        f"USING {volunteer} WITH CHECK {volunteer}"
    )
    # Provider role: own provider organization only.
    own_po = "(provider_organization_id = app_current_provider_org())"
    for t in ("activity", "provider_scope", "export_record", "share_event"):
        op.execute(
            f"CREATE POLICY provider_own ON {t} AS RESTRICTIVE TO csl_provider "
            f"USING {own_po} WITH CHECK {own_po}"
        )
    op.execute(
        "CREATE POLICY provider_own ON provider_organization AS RESTRICTIVE TO csl_provider "
        "USING (id = app_current_provider_org())"
    )
    op.execute(
        "CREATE POLICY provider_own ON activity_area AS RESTRICTIVE TO csl_provider "
        "USING (EXISTS (SELECT 1 FROM activity a WHERE a.id = activity_id "
        "AND a.organization_id = activity_area.organization_id "
        "AND a.provider_organization_id = app_current_provider_org()))"
    )
    own_member = "(membership_id = app_current_actor())"
    for t in ("alert_subscription", "api_key"):
        op.execute(
            f"CREATE POLICY provider_own ON {t} AS RESTRICTIVE TO csl_provider "
            f"USING {own_member} WITH CHECK {own_member}"
        )
    op.execute(
        "CREATE POLICY provider_own ON alert_subscription_area AS RESTRICTIVE TO csl_provider "
        "USING (EXISTS (SELECT 1 FROM alert_subscription s WHERE s.id = alert_subscription_id "
        "AND s.organization_id = alert_subscription_area.organization_id "
        "AND s.membership_id = app_current_actor()))"
    )
    # API keys are looked up by hash before the tenant is known (db.lookup_api_key).
    op.execute(
        "CREATE POLICY api_key_lookup ON api_key FOR SELECT TO csl_runtime "
        "USING (key_hash = nullif(current_setting('app.api_key_hash', true), ''))"
    )
    # Public snapshots are readable only while the active profile enables the dashboard.
    for t in ("public_indicator_cell", "public_activity"):
        op.execute(
            f"CREATE POLICY public_enabled ON {t} AS RESTRICTIVE FOR SELECT TO csl_public "
            f"USING (app_public_dashboard_enabled(organization_id))"
        )

    op.execute(TRIGGERS_SQL)
    for t in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{t}_append_only BEFORE UPDATE OR DELETE ON {t} "
            f"FOR EACH ROW EXECUTE FUNCTION app_forbid_mutation()"
        )

    op.execute(VIEWS_SQL)

    # --- grants (DB-004) ---
    plain = [t for t in TENANT_TABLES if t not in APPEND_ONLY_TABLES + DERIVED_TABLES]
    _grant("SELECT, INSERT, UPDATE, DELETE", plain, ("csl_runtime", "csl_worker"))
    _grant("SELECT, INSERT", APPEND_ONLY_TABLES, ("csl_runtime", "csl_worker"))
    _grant("SELECT", DERIVED_TABLES, ("csl_runtime",))
    _grant("SELECT, INSERT, UPDATE, DELETE", DERIVED_TABLES, ("csl_worker",))
    _grant("SELECT, INSERT, UPDATE, DELETE", UNSECURED_APP_TABLES, ("csl_runtime", "csl_worker"))
    _grant("SELECT, INSERT", QUEUE_TABLES, ("csl_runtime",))
    _grant("SELECT, INSERT, UPDATE, DELETE", QUEUE_TABLES, ("csl_worker",))
    _grant("SELECT", ("v_indicator_cell", "v_coverage_cell", "v_activity"),
           ("csl_runtime", "csl_worker", "csl_provider", "csl_analyst"))
    _grant("SELECT", ("provider_contact_list",), ("csl_provider",))
    # Providers: reference data, own activity log, alerts, API keys, exports.
    _grant("SELECT", ("area", "area_alias", "area_boundary", "meeting_point",
                      "external_indicator", "provider_organization", "provider_scope"),
           ("csl_provider", "csl_analyst"))
    _grant("SELECT, INSERT, UPDATE", ("activity", "alert_subscription", "api_key"),
           ("csl_provider",))
    _grant("SELECT, INSERT, DELETE", ("activity_area", "alert_subscription_area"),
           ("csl_provider",))
    _grant("SELECT, INSERT", ("export_record",), ("csl_provider", "csl_analyst"))
    _grant("INSERT", ("share_event", "audit_event", "job"), ("csl_provider", "csl_analyst"))
    # Public: snapshots only.
    _grant("SELECT", ("public_indicator_cell", "public_activity"), ("csl_public",))


def _drop_postgres_objects_before_tables() -> None:
    for v in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {v}")
    # Group roles are cluster-wide and are kept; remove their grants on tables
    # that survive the downgrade.
    op.execute(
        f"REVOKE ALL ON {', '.join(UNSECURED_APP_TABLES + QUEUE_TABLES)} "
        f"FROM {', '.join(RUNTIME_ROLES)}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {', '.join(RUNTIME_ROLES)}")


def _drop_postgres_functions() -> None:
    for fn in ("resolve_area_for_point(geometry)", "app_public_dashboard_enabled(text)",
               "app_fill_from_report()",
               "app_forbid_mutation()", "app_profile_version_guard()",
               "app_enforce_report_location_profile()", "app_enforce_report_profile()",
               "app_current_provider_org()", "app_current_role()", "app_current_actor()",
               "app_current_org()"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")




def upgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    if pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    _rename_legacy_tables(pg)

    # Composite-FK targets and adapted system tables, before new tables reference them.
    with op.batch_alter_table('household', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_household_org_id', ['organization_id', 'id'])

    with op.batch_alter_table('idempotency_key', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actor_scope', sa.String(length=80), server_default='', nullable=False))
        batch_op.add_column(sa.Column('request_digest', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.drop_constraint(batch_op.f('uq_idempotency'), type_='unique')
        batch_op.create_unique_constraint('uq_idempotency', ['organization_id', 'actor_scope', 'endpoint', 'key'])

    with op.batch_alter_table('inbound_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=16), server_default='received', nullable=False))
        batch_op.add_column(sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_inbound_event_pending', ['status', 'received_at'], unique=False)

    with op.batch_alter_table('organization_membership', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_organization_id', sa.String(length=36), nullable=True))
        batch_op.create_unique_constraint('uq_organization_membership_org_id', ['organization_id', 'id'])

    # ---- pilot tables (autogenerated, reviewed) ----
    op.create_table('job',
    sa.Column('organization_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_owner', sa.String(length=100), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'dead')", name='ck_job_status'),
    sa.CheckConstraint('attempts >= 0 AND max_attempts > 0', name='ck_job_attempts'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key', name='uq_job_dedupe_key')
    )
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.create_index('ix_job_claim', ['status', 'run_after', 'priority'], unique=False)

    op.create_table('message_status_event',
    sa.Column('channel_account_id', sa.String(length=128), nullable=False),
    sa.Column('provider_message_id', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel_account_id', 'provider_message_id', 'status', name='uq_message_status_event')
    )
    op.create_table('area',
    sa.Column('parent_area_id', sa.String(length=36), nullable=True),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('official_code', sa.String(length=64), nullable=True),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'retired')", name='ck_area_status'),
    sa.CheckConstraint("type IN ('state', 'municipality', 'parish', 'sector')", name='ck_area_type'),
    sa.CheckConstraint('parent_area_id IS NULL OR parent_area_id <> id', name='ck_area_not_own_parent'),
    sa.ForeignKeyConstraint(['organization_id', 'parent_area_id'], ['area.organization_id', 'area.id'], name='fk_area_parent_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_area_org_id')
    )
    with op.batch_alter_table('area', schema=None) as batch_op:
        batch_op.create_index('ix_area_org_parent', ['organization_id', 'parent_area_id'], unique=False)
        batch_op.create_index('uq_area_code', ['organization_id', 'type', 'official_code'], unique=True)

    op.create_table('audit_event',
    sa.Column('actor_ref', sa.String(length=80), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('redacted_change_summary', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_audit_event_org_id')
    )
    with op.batch_alter_table('audit_event', schema=None) as batch_op:
        batch_op.create_index('ix_audit_event_entity', ['organization_id', 'entity_type', 'entity_id'], unique=False)
        batch_op.create_index('ix_audit_event_org_time', ['organization_id', 'occurred_at'], unique=False)

    op.create_table('contact_endpoint',
    sa.Column('channel', sa.String(length=32), nullable=False),
    sa.Column('encrypted_address', sa.LargeBinary(), nullable=True),
    sa.Column('address_lookup_hmac', sa.String(length=128), nullable=False),
    sa.Column('key_version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opted_out_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('whatsapp', 'sms', 'phone', 'volunteer_assisted')", name='ck_contact_endpoint_channel'),
    sa.CheckConstraint("status <> 'deleted' OR encrypted_address IS NULL", name='ck_contact_endpoint_deleted_no_address'),
    sa.CheckConstraint("status IN ('active', 'opted_out', 'deleted')", name='ck_contact_endpoint_status'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'channel', 'address_lookup_hmac', name='uq_contact_endpoint_lookup'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_contact_endpoint_org_id')
    )
    op.create_table('data_job',
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('params_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('lease_fence', sa.Integer(), nullable=False),
    sa.Column('lease_owner', sa.String(length=100), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('run_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'leased', 'succeeded', 'failed', 'cancelled')", name='ck_data_job_status'),
    sa.CheckConstraint('attempts >= 0 AND lease_fence >= 0', name='ck_data_job_counters'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_data_job_org_id')
    )
    with op.batch_alter_table('data_job', schema=None) as batch_op:
        batch_op.create_index('ix_data_job_claim', ['status', 'run_after'], unique=False)

    op.create_table('policy_version',
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('body_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('retention', 'urgency', 'vetting', 'data_handling_statement', 'other')", name='ck_policy_version_kind'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_policy_version_org_id')
    )
    with op.batch_alter_table('policy_version', schema=None) as batch_op:
        batch_op.create_index('uq_policy_version', ['organization_id', 'kind', 'version'], unique=True)

    op.create_table('questionnaire_version',
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=False),
    sa.Column('definition_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_questionnaire_version_org_id')
    )
    with op.batch_alter_table('questionnaire_version', schema=None) as batch_op:
        batch_op.create_index('uq_questionnaire_version', ['organization_id', 'version', 'language'], unique=True)

    op.create_table('alert_subscription',
    sa.Column('membership_id', sa.String(length=36), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('trigger', sa.String(length=32), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=True),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('window_hours', sa.Integer(), nullable=False),
    sa.Column('muted', sa.Boolean(), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_alert_subscription_category'),
    sa.CheckConstraint("channel IN ('email', 'whatsapp', 'in_app')", name='ck_alert_subscription_channel'),
    sa.CheckConstraint("trigger <> 'active_needs_above' OR threshold IS NOT NULL", name='ck_alert_threshold_required'),
    sa.CheckConstraint("trigger IN ('new_urgent_needs', 'active_needs_above', 'area_uncovered', 'external_outage_signal')", name='ck_alert_subscription_trigger'),
    sa.CheckConstraint('threshold IS NULL OR threshold >= 0', name='ck_alert_threshold'),
    sa.CheckConstraint('window_hours > 0', name='ck_alert_window'),
    sa.ForeignKeyConstraint(['organization_id', 'membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_alert_subscription_membership_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_alert_subscription_org_id')
    )
    op.create_table('area_alias',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('alias', sa.String(length=200), nullable=False),
    sa.Column('normalized_alias', sa.String(length=200), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_area_alias_area_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_area_alias_org_id')
    )
    with op.batch_alter_table('area_alias', schema=None) as batch_op:
        batch_op.create_index('uq_area_alias', ['organization_id', 'normalized_alias', 'area_id'], unique=True)

    op.create_table('area_boundary',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('boundary', _geom('MULTIPOLYGON', pg), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('valid_to IS NULL OR valid_from <= valid_to', name='ck_area_boundary_range'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_area_boundary_area_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_area_boundary_org_id')
    )
    with op.batch_alter_table('area_boundary', schema=None) as batch_op:
        batch_op.create_index('uq_area_boundary_version', ['organization_id', 'area_id', 'version'], unique=True)

    op.create_table('campaign',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('display_identity', sa.String(length=100), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('questionnaire_version_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'ended')", name='ck_campaign_status'),
    sa.CheckConstraint('ends_at IS NULL OR starts_at <= ends_at', name='ck_campaign_range'),
    sa.ForeignKeyConstraint(['organization_id', 'questionnaire_version_id'], ['questionnaire_version.organization_id', 'questionnaire_version.id'], name='fk_campaign_questionnaire_version_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_campaign_org_id')
    )
    op.create_table('coverage_cell',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('coverage', sa.String(length=16), nullable=False),
    sa.Column('activity_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('method_version', sa.String(length=32), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_coverage_cell_category'),
    sa.CheckConstraint("coverage IN ('covered', 'uncovered', 'unknown')", name='ck_coverage_cell_coverage'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_coverage_cell_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'area_id', 'category', 'method_version', name='uq_coverage_cell'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_coverage_cell_org_id')
    )
    op.create_table('data_job_result',
    sa.Column('data_job_id', sa.String(length=36), nullable=False),
    sa.Column('lease_fence', sa.Integer(), nullable=False),
    sa.Column('summary_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('object_reference', sa.String(length=300), nullable=True),
    sa.Column('checksum', sa.String(length=128), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('content_type', sa.String(length=100), nullable=True),
    sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'data_job_id'], ['data_job.organization_id', 'data_job.id'], name='fk_data_job_result_data_job_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('data_job_id', 'lease_fence', name='uq_data_job_result_fence'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_data_job_result_org_id')
    )
    op.create_table('duplicate_candidate',
    sa.Column('entity_type', sa.String(length=16), nullable=False),
    sa.Column('entity_a_id', sa.String(length=36), nullable=False),
    sa.Column('entity_b_id', sa.String(length=36), nullable=False),
    sa.Column('match_reasons', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('rule_version', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('reviewed_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("entity_type IN ('report', 'observation', 'need')", name='ck_duplicate_candidate_entity_type'),
    sa.CheckConstraint("status IN ('open', 'confirmed', 'rejected')", name='ck_duplicate_candidate_status'),
    sa.CheckConstraint('entity_a_id < entity_b_id', name='ck_duplicate_candidate_order'),
    sa.ForeignKeyConstraint(['organization_id', 'reviewed_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_duplicate_candidate_reviewed_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'entity_type', 'entity_a_id', 'entity_b_id', name='uq_duplicate_candidate'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_duplicate_candidate_org_id')
    )
    op.create_table('external_indicator',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('source_label', sa.String(length=200), nullable=False),
    sa.Column('subject', sa.String(length=32), nullable=False),
    sa.Column('indicator', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column('unit', sa.String(length=32), nullable=True),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("subject IN ('electricity', 'piped_water', 'water_drinking', 'water_other', 'charging')", name='ck_external_indicator_subject'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_external_indicator_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_external_indicator_org_id')
    )
    with op.batch_alter_table('external_indicator', schema=None) as batch_op:
        batch_op.create_index('ix_external_indicator_lookup', ['organization_id', 'area_id', 'subject', 'observed_at'], unique=False)

    op.create_table('indicator_dirty_cell',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('subject', sa.String(length=32), nullable=False),
    sa.Column('since', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("subject IN ('water_drinking', 'water_other', 'charging', 'electricity', 'piped_water')", name='ck_indicator_dirty_cell_subject'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_indicator_dirty_cell_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'area_id', 'subject', name='uq_indicator_dirty_cell'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_indicator_dirty_cell_org_id')
    )
    op.create_table('meeting_point',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('public_description', sa.Text(), nullable=True),
    sa.Column('public_point', _geom('POINT', pg), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('plaza', 'church', 'school', 'bodega', 'health_center', 'community_center', 'other')", name='ck_meeting_point_kind'),
    sa.CheckConstraint("status IN ('active', 'inactive')", name='ck_meeting_point_status'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_meeting_point_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_meeting_point_org_id')
    )
    with op.batch_alter_table('meeting_point', schema=None) as batch_op:
        batch_op.create_index('ix_meeting_point_org_area', ['organization_id', 'area_id', 'status'], unique=False)

    op.create_table('merge_event',
    sa.Column('entity_type', sa.String(length=16), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('destination_id', sa.String(length=36), nullable=False),
    sa.Column('approved_by_membership_id', sa.String(length=36), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reverses_merge_event_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("entity_type IN ('report', 'observation', 'need')", name='ck_merge_event_entity_type'),
    sa.CheckConstraint('source_id <> destination_id', name='ck_merge_event_distinct'),
    sa.ForeignKeyConstraint(['organization_id', 'approved_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_merge_event_approved_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'reverses_merge_event_id'], ['merge_event.organization_id', 'merge_event.id'], name='fk_merge_event_reverses_merge_event_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_merge_event_org_id')
    )
    op.create_table('outage_episode',
    sa.Column('service_type', sa.String(length=32), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('assessment_basis', sa.String(length=64), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("service_type IN ('electricity', 'piped_water')", name='ck_outage_episode_service_type'),
    sa.CheckConstraint("status IN ('suspected', 'confirmed', 'ended', 'dismissed')", name='ck_outage_episode_status'),
    sa.CheckConstraint('ended_at IS NULL OR started_at IS NULL OR started_at <= ended_at', name='ck_outage_episode_range'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_outage_episode_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_outage_episode_org_id')
    )
    op.create_table('privacy_profile_version',
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('profile_key', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('names_allowed', sa.Boolean(), nullable=False),
    sa.Column('location_mode', sa.String(length=16), nullable=False),
    sa.Column('gps_allowed', sa.Boolean(), nullable=False),
    sa.Column('household_records_allowed', sa.Boolean(), nullable=False),
    sa.Column('contact_list_allowed', sa.Boolean(), nullable=False),
    sa.Column('contact_list_fields', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('reporter_phone_retention_days', sa.Integer(), nullable=False),
    sa.Column('reporter_key_rotation_days', sa.Integer(), nullable=False),
    sa.Column('report_retention_days', sa.Integer(), nullable=False),
    sa.Column('aggregate_k', sa.Integer(), nullable=False),
    sa.Column('public_dashboard_enabled', sa.Boolean(), nullable=False),
    sa.Column('public_level', sa.String(length=16), nullable=False),
    sa.Column('public_k', sa.Integer(), nullable=False),
    sa.Column('public_delay_hours', sa.Integer(), nullable=False),
    sa.Column('settings_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('notice_version', sa.String(length=32), nullable=False),
    sa.Column('activated_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("NOT gps_allowed OR location_mode = 'address'", name='ck_profile_gps_needs_address'),
    sa.CheckConstraint("location_mode IN ('meeting_point', 'address')", name='ck_privacy_profile_version_location_mode'),
    sa.CheckConstraint("profile_key IN ('protective', 'standard')", name='ck_privacy_profile_version_profile_key'),
    sa.CheckConstraint("public_level IN ('parish', 'sector')", name='ck_privacy_profile_version_public_level'),
    sa.CheckConstraint("status = 'draft' OR activated_at IS NOT NULL", name='ck_profile_activated_at'),
    sa.CheckConstraint("status IN ('draft', 'active', 'retired')", name='ck_privacy_profile_version_status'),
    sa.CheckConstraint('aggregate_k >= 3', name='ck_profile_aggregate_k'),
    sa.CheckConstraint('public_delay_hours >= 0', name='ck_profile_public_delay'),
    sa.CheckConstraint('public_k >= 3', name='ck_profile_public_k'),
    sa.ForeignKeyConstraint(['organization_id', 'activated_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_privacy_profile_version_activated_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_privacy_profile_version_org_id')
    )
    with op.batch_alter_table('privacy_profile_version', schema=None) as batch_op:
        batch_op.create_index('uq_privacy_profile_active', ['organization_id'], unique=True, postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
        batch_op.create_index('uq_privacy_profile_version', ['organization_id', 'version'], unique=True)

    op.create_table('provider_organization',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('vetting_status', sa.String(length=16), nullable=False),
    sa.Column('vetting_reason', sa.Text(), nullable=True),
    sa.Column('vetting_changed_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('vetting_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('responsible_contact_reference', sa.String(length=200), nullable=True),
    sa.Column('statement_version', sa.String(length=32), nullable=True),
    sa.Column('may_disclose_name', sa.Boolean(), nullable=False),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("vetting_status IN ('unvetted', 'vetted', 'suspended')", name='ck_provider_organization_vetting_status'),
    sa.ForeignKeyConstraint(['organization_id', 'vetting_changed_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_provider_organization_vetting_changed_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_provider_organization_org_id'),
    sa.UniqueConstraint('organization_id', 'name', name='uq_provider_organization_name')
    )
    op.create_table('public_activity',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('provider_name', sa.String(length=200), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('area_name', sa.String(length=200), nullable=False),
    sa.Column('schedule_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('public_location_description', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_public_activity_category'),
    sa.CheckConstraint("type IN ('water_distribution_point', 'water_delivery', 'charging_point', 'other')", name='ck_public_activity_type'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_public_activity_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_public_activity_org_id')
    )
    op.create_table('public_indicator_cell',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('area_name', sa.String(length=200), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('subject', sa.String(length=32), nullable=False),
    sa.Column('bucket', sa.String(length=8), nullable=False),
    sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status_mix', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('need_count_band', sa.String(length=16), nullable=True),
    sa.Column('coverage_label', sa.String(length=16), nullable=False),
    sa.Column('freshness_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("bucket IN ('6h', '24h', '7d')", name='ck_public_indicator_cell_bucket'),
    sa.CheckConstraint("coverage_label IN ('none', 'thin', 'reported')", name='ck_public_indicator_cell_coverage_label'),
    sa.CheckConstraint("level IN ('sector', 'parish', 'municipality', 'state')", name='ck_public_indicator_cell_level'),
    sa.CheckConstraint("subject IN ('water_drinking', 'water_other', 'charging', 'electricity', 'piped_water')", name='ck_public_indicator_cell_subject'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_public_indicator_cell_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'area_id', 'subject', 'bucket', 'bucket_start', name='uq_public_indicator_cell'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_public_indicator_cell_org_id')
    )
    op.create_table('reporter_key',
    sa.Column('key_hmac', sa.String(length=128), nullable=False),
    sa.Column('epoch', sa.Integer(), nullable=False),
    sa.Column('contact_endpoint_id', sa.String(length=36), nullable=True),
    sa.Column('alias', sa.String(length=32), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('expires_at IS NULL OR expires_at > created_at', name='ck_reporter_key_expiry'),
    sa.ForeignKeyConstraint(['organization_id', 'contact_endpoint_id'], ['contact_endpoint.organization_id', 'contact_endpoint.id'], name='fk_reporter_key_contact_endpoint_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_reporter_key_org_id'),
    sa.UniqueConstraint('organization_id', 'key_hmac', name='uq_reporter_key_hmac')
    )
    with op.batch_alter_table('reporter_key', schema=None) as batch_op:
        batch_op.create_index('ix_reporter_key_endpoint', ['organization_id', 'contact_endpoint_id', 'epoch'], unique=False)

    op.create_table('activity',
    sa.Column('provider_organization_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('schedule_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('capacity', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('capacity_unit', sa.String(length=16), nullable=True),
    sa.Column('public_meeting_point_id', sa.String(length=36), nullable=True),
    sa.Column('public_location_description', sa.String(length=300), nullable=True),
    sa.Column('visibility', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("capacity_unit IS NULL OR (capacity_unit = 'liters_per_day' AND category IN ('water_drinking', 'water_other')) OR (capacity_unit = 'devices_per_day' AND category = 'charging')", name='ck_activity_capacity_unit_category'),
    sa.CheckConstraint("capacity_unit IS NULL OR capacity_unit IN ('liters_per_day', 'devices_per_day')", name='ck_activity_capacity_unit'),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_activity_category'),
    sa.CheckConstraint("status IN ('planned', 'active', 'paused', 'ended')", name='ck_activity_status'),
    sa.CheckConstraint("type IN ('water_distribution_point', 'water_delivery', 'charging_point', 'other')", name='ck_activity_type'),
    sa.CheckConstraint("visibility IN ('tenant', 'internal', 'public')", name='ck_activity_visibility'),
    sa.CheckConstraint('capacity IS NULL OR (capacity >= 0 AND capacity_unit IS NOT NULL)', name='ck_activity_capacity'),
    sa.CheckConstraint('ends_at IS NULL OR starts_at IS NULL OR starts_at <= ends_at', name='ck_activity_range'),
    sa.ForeignKeyConstraint(['organization_id', 'created_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_activity_created_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'provider_organization_id'], ['provider_organization.organization_id', 'provider_organization.id'], name='fk_activity_provider_organization_id'),
    sa.ForeignKeyConstraint(['organization_id', 'public_meeting_point_id'], ['meeting_point.organization_id', 'meeting_point.id'], name='fk_activity_public_meeting_point_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_activity_org_id')
    )
    with op.batch_alter_table('activity', schema=None) as batch_op:
        batch_op.create_index('ix_activity_org_status', ['organization_id', 'category', 'status'], unique=False)
        batch_op.create_index('ix_activity_provider', ['organization_id', 'provider_organization_id'], unique=False)

    op.create_table('alert_delivery',
    sa.Column('alert_subscription_id', sa.String(length=36), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('trigger_key', sa.String(length=200), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('payload_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('outbox_reference', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('email', 'whatsapp', 'in_app')", name='ck_alert_delivery_channel'),
    sa.ForeignKeyConstraint(['organization_id', 'alert_subscription_id'], ['alert_subscription.organization_id', 'alert_subscription.id'], name='fk_alert_delivery_alert_subscription_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'alert_subscription_id', 'window_start', 'trigger_key', name='uq_alert_delivery_window'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_alert_delivery_org_id')
    )
    op.create_table('alert_subscription_area',
    sa.Column('alert_subscription_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'alert_subscription_id'], ['alert_subscription.organization_id', 'alert_subscription.id'], name='fk_alert_subscription_area_alert_subscription_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_alert_subscription_area_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'alert_subscription_id', 'area_id', name='uq_alert_subscription_area'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_alert_subscription_area_org_id')
    )
    op.create_table('api_key',
    sa.Column('membership_id', sa.String(length=36), nullable=False),
    sa.Column('provider_organization_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('key_prefix', sa.String(length=16), nullable=False),
    sa.Column('key_hash', sa.String(length=128), nullable=False),
    sa.Column('scopes', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('revoked_at IS NULL OR revoked_at >= created_at', name='ck_api_key_revoked'),
    sa.ForeignKeyConstraint(['organization_id', 'membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_api_key_membership_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'provider_organization_id'], ['provider_organization.organization_id', 'provider_organization.id'], name='fk_api_key_provider_organization_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key_hash', name='uq_api_key_hash'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_api_key_org_id')
    )
    op.create_table('campaign_area',
    sa.Column('campaign_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_campaign_area_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'campaign_id'], ['campaign.organization_id', 'campaign.id'], name='fk_campaign_area_campaign_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_campaign_area_org_id')
    )
    with op.batch_alter_table('campaign_area', schema=None) as batch_op:
        batch_op.create_index('uq_campaign_area', ['organization_id', 'campaign_id', 'area_id'], unique=True)

    op.create_table('conversation',
    sa.Column('contact_endpoint_id', sa.String(length=36), nullable=True),
    sa.Column('campaign_id', sa.String(length=36), nullable=True),
    sa.Column('questionnaire_version_id', sa.String(length=36), nullable=True),
    sa.Column('intake_state', sa.String(length=64), nullable=False),
    sa.Column('last_user_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('assigned_membership_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'assigned_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_conversation_assigned_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'campaign_id'], ['campaign.organization_id', 'campaign.id'], name='fk_conversation_campaign_id'),
    sa.ForeignKeyConstraint(['organization_id', 'contact_endpoint_id'], ['contact_endpoint.organization_id', 'contact_endpoint.id'], name='fk_conversation_contact_endpoint_id'),
    sa.ForeignKeyConstraint(['organization_id', 'questionnaire_version_id'], ['questionnaire_version.organization_id', 'questionnaire_version.id'], name='fk_conversation_questionnaire_version_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_conversation_org_id')
    )
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.create_index('ix_conversation_endpoint', ['organization_id', 'contact_endpoint_id'], unique=False)

    op.create_table('indicator_cell',
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('subject', sa.String(length=32), nullable=False),
    sa.Column('bucket', sa.String(length=8), nullable=False),
    sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active_needs', sa.Integer(), nullable=False),
    sa.Column('distinct_reporters', sa.Integer(), nullable=False),
    sa.Column('distinct_households', sa.Integer(), nullable=True),
    sa.Column('people_known', sa.Integer(), nullable=False),
    sa.Column('people_unknown_count', sa.Integer(), nullable=False),
    sa.Column('urgency_mix', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('supply_mix', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status_mix', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('pending_review_share', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('freshness_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('coverage_label', sa.String(length=16), nullable=False),
    sa.Column('confidence_label', sa.String(length=16), nullable=False),
    sa.Column('confidence_reasons', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('suppressed', sa.Boolean(), nullable=False),
    sa.Column('method_version', sa.String(length=32), nullable=False),
    sa.Column('profile_version_id', sa.String(length=36), nullable=False),
    sa.Column('input_watermark', sa.DateTime(timezone=True), nullable=True),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("bucket IN ('6h', '24h', '7d')", name='ck_indicator_cell_bucket'),
    sa.CheckConstraint("confidence_label IN ('low', 'medium', 'high')", name='ck_indicator_cell_confidence_label'),
    sa.CheckConstraint("coverage_label IN ('none', 'thin', 'reported')", name='ck_indicator_cell_coverage_label'),
    sa.CheckConstraint("level IN ('sector', 'parish', 'municipality', 'state')", name='ck_indicator_cell_level'),
    sa.CheckConstraint("subject IN ('water_drinking', 'water_other', 'charging', 'electricity', 'piped_water')", name='ck_indicator_cell_subject'),
    sa.CheckConstraint('active_needs >= 0 AND distinct_reporters >= 0 AND people_known >= 0 AND people_unknown_count >= 0 AND (distinct_households IS NULL OR distinct_households >= 0)', name='ck_indicator_cell_counts'),
    sa.CheckConstraint('pending_review_share IS NULL OR (pending_review_share >= 0 AND pending_review_share <= 1)', name='ck_indicator_cell_review_share'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_indicator_cell_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'profile_version_id'], ['privacy_profile_version.organization_id', 'privacy_profile_version.id'], name='fk_indicator_cell_profile_version_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'area_id', 'subject', 'bucket', 'bucket_start', 'method_version', name='uq_indicator_cell'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_indicator_cell_org_id')
    )
    with op.batch_alter_table('indicator_cell', schema=None) as batch_op:
        batch_op.create_index('ix_indicator_cell_lookup', ['organization_id', 'area_id', 'subject', 'bucket', 'bucket_start'], unique=False)

    op.create_table('permission',
    sa.Column('reporter_key_id', sa.String(length=36), nullable=True),
    sa.Column('contact_endpoint_id', sa.String(length=36), nullable=True),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('notice_version', sa.String(length=32), nullable=False),
    sa.Column('processing_basis', sa.String(length=64), nullable=True),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence_reference', sa.String(length=200), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision IN ('granted', 'denied')", name='ck_permission_decision'),
    sa.CheckConstraint("purpose IN ('notice_ack', 'refresh_prompts', 'area_broadcasts', 'contact_list')", name='ck_permission_purpose'),
    sa.CheckConstraint('reporter_key_id IS NOT NULL OR contact_endpoint_id IS NOT NULL', name='ck_permission_subject'),
    sa.CheckConstraint('withdrawn_at IS NULL OR withdrawn_at >= captured_at', name='ck_permission_withdrawn_after_capture'),
    sa.ForeignKeyConstraint(['organization_id', 'contact_endpoint_id'], ['contact_endpoint.organization_id', 'contact_endpoint.id'], name='fk_permission_contact_endpoint_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'reporter_key_id'], ['reporter_key.organization_id', 'reporter_key.id'], name='fk_permission_reporter_key_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_permission_org_id')
    )
    with op.batch_alter_table('permission', schema=None) as batch_op:
        batch_op.create_index('ix_permission_endpoint', ['organization_id', 'contact_endpoint_id', 'purpose'], unique=False)
        batch_op.create_index('ix_permission_subject', ['organization_id', 'reporter_key_id', 'purpose'], unique=False)

    op.create_table('provider_scope',
    sa.Column('provider_organization_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_provider_scope_category'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_provider_scope_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'provider_organization_id'], ['provider_organization.organization_id', 'provider_organization.id'], name='fk_provider_scope_provider_organization_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_provider_scope_org_id'),
    sa.UniqueConstraint('organization_id', 'provider_organization_id', 'area_id', 'category', name='uq_provider_scope')
    )
    op.create_table('activity_area',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'activity_id'], ['activity.organization_id', 'activity.id'], name='fk_activity_area_activity_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_activity_area_area_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'activity_id', 'area_id', name='uq_activity_area'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_activity_area_org_id')
    )
    with op.batch_alter_table('activity_area', schema=None) as batch_op:
        batch_op.create_index('ix_activity_area_area', ['organization_id', 'area_id'], unique=False)

    op.create_table('broadcast',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('template_name', sa.String(length=100), nullable=False),
    sa.Column('template_params', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('approved_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('recipient_count', sa.Integer(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'approved', 'sending', 'sent', 'cancelled')", name='ck_broadcast_status'),
    sa.CheckConstraint("status NOT IN ('approved', 'sending', 'sent') OR approved_by_membership_id IS NOT NULL", name='ck_broadcast_approved'),
    sa.CheckConstraint('recipient_count >= 0', name='ck_broadcast_recipients'),
    sa.ForeignKeyConstraint(['organization_id', 'activity_id'], ['activity.organization_id', 'activity.id'], name='fk_broadcast_activity_id'),
    sa.ForeignKeyConstraint(['organization_id', 'approved_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_broadcast_approved_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_broadcast_org_id')
    )
    op.create_table('export_record',
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('membership_id', sa.String(length=36), nullable=True),
    sa.Column('api_key_id', sa.String(length=36), nullable=True),
    sa.Column('provider_organization_id', sa.String(length=36), nullable=True),
    sa.Column('filters_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('watermark', sa.String(length=64), nullable=True),
    sa.Column('input_watermark', sa.DateTime(timezone=True), nullable=True),
    sa.Column('object_reference', sa.String(length=300), nullable=True),
    sa.Column('checksum', sa.String(length=128), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('aggregate', 'contact_list', 'activity')", name='ck_export_record_kind'),
    sa.CheckConstraint('row_count >= 0', name='ck_export_record_rows'),
    sa.ForeignKeyConstraint(['organization_id', 'api_key_id'], ['api_key.organization_id', 'api_key.id'], name='fk_export_record_api_key_id'),
    sa.ForeignKeyConstraint(['organization_id', 'membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_export_record_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'provider_organization_id'], ['provider_organization.organization_id', 'provider_organization.id'], name='fk_export_record_provider_organization_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_export_record_org_id')
    )
    op.create_table('message',
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('channel_account_id', sa.String(length=128), nullable=False),
    sa.Column('provider_message_id', sa.String(length=128), nullable=True),
    sa.Column('direction', sa.String(length=16), nullable=False),
    sa.Column('content_reference', sa.String(length=300), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivery_status', sa.String(length=16), nullable=False),
    sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("delivery_status IN ('received', 'queued', 'sent', 'delivered', 'read', 'failed')", name='ck_message_delivery_status'),
    sa.CheckConstraint("direction IN ('inbound', 'outbound')", name='ck_message_direction'),
    sa.ForeignKeyConstraint(['organization_id', 'conversation_id'], ['conversation.organization_id', 'conversation.id'], name='fk_message_conversation_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('channel_account_id', 'provider_message_id', name='uq_message_provider_id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_message_org_id')
    )
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.create_index('ix_message_conversation', ['organization_id', 'conversation_id'], unique=False)

    op.create_table('outbox_message',
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('contact_endpoint_id', sa.String(length=36), nullable=True),
    sa.Column('conversation_id', sa.String(length=36), nullable=True),
    sa.Column('template_name', sa.String(length=100), nullable=True),
    sa.Column('template_params', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('body_reference', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('block_reason', sa.String(length=64), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('provider_message_id', sa.String(length=128), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("purpose IN ('conversation_reply', 'refresh_prompt', 'area_broadcast', 'alert', 'opt_out_confirmation', 'notice')", name='ck_outbox_message_purpose'),
    sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'blocked', 'failed')", name='ck_outbox_message_status'),
    sa.ForeignKeyConstraint(['organization_id', 'contact_endpoint_id'], ['contact_endpoint.organization_id', 'contact_endpoint.id'], name='fk_outbox_message_contact_endpoint_id'),
    sa.ForeignKeyConstraint(['organization_id', 'conversation_id'], ['conversation.organization_id', 'conversation.id'], name='fk_outbox_message_conversation_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'dedupe_key', name='uq_outbox_dedupe'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_outbox_message_org_id')
    )
    with op.batch_alter_table('outbox_message', schema=None) as batch_op:
        batch_op.create_index('ix_outbox_pending', ['organization_id', 'status', 'next_attempt_at'], unique=False)

    op.create_table('report',
    sa.Column('privacy_profile_version_id', sa.String(length=36), nullable=False),
    sa.Column('reporter_key_id', sa.String(length=36), nullable=True),
    sa.Column('household_id', sa.String(length=36), nullable=True),
    sa.Column('campaign_id', sa.String(length=36), nullable=True),
    sa.Column('conversation_id', sa.String(length=36), nullable=True),
    sa.Column('questionnaire_version_id', sa.String(length=36), nullable=True),
    sa.Column('source_channel', sa.String(length=32), nullable=False),
    sa.Column('reporting_relationship', sa.String(length=32), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=True),
    sa.Column('location_kind', sa.String(length=16), nullable=False),
    sa.Column('meeting_point_id', sa.String(length=36), nullable=True),
    sa.Column('encrypted_reporter_name', sa.LargeBinary(), nullable=True),
    sa.Column('answers_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('supersedes_report_id', sa.String(length=36), nullable=True),
    sa.Column('entered_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('urgent_flagged', sa.Boolean(), nullable=False),
    sa.Column('excluded_reason', sa.String(length=16), nullable=True),
    sa.Column('excluded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("excluded_reason IS NULL OR excluded_reason IN ('duplicate', 'spam')", name='ck_report_excluded_reason'),
    sa.CheckConstraint("location_kind <> 'meeting_point' OR meeting_point_id IS NOT NULL", name='ck_report_meeting_point'),
    sa.CheckConstraint("location_kind IN ('meeting_point', 'none_nearby', 'address', 'area_only', 'unresolved')", name='ck_report_location_kind'),
    sa.CheckConstraint("reporting_relationship IN ('self', 'household', 'other_person', 'area')", name='ck_report_reporting_relationship'),
    sa.CheckConstraint("source_channel IN ('whatsapp', 'phone', 'volunteer_assisted')", name='ck_report_source_channel'),
    sa.CheckConstraint("status <> 'confirmed' OR confirmed_at IS NOT NULL", name='ck_report_confirmed_at'),
    sa.CheckConstraint("status IN ('draft', 'confirmed', 'superseded', 'withdrawn', 'abandoned')", name='ck_report_status'),
    sa.CheckConstraint('supersedes_report_id IS NULL OR supersedes_report_id <> id', name='ck_report_no_self_supersede'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_report_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'campaign_id'], ['campaign.organization_id', 'campaign.id'], name='fk_report_campaign_id'),
    sa.ForeignKeyConstraint(['organization_id', 'conversation_id'], ['conversation.organization_id', 'conversation.id'], name='fk_report_conversation_id'),
    sa.ForeignKeyConstraint(['organization_id', 'entered_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_report_entered_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'household_id'], ['household.organization_id', 'household.id'], name='fk_report_household_id'),
    sa.ForeignKeyConstraint(['organization_id', 'meeting_point_id'], ['meeting_point.organization_id', 'meeting_point.id'], name='fk_report_meeting_point_id'),
    sa.ForeignKeyConstraint(['organization_id', 'privacy_profile_version_id'], ['privacy_profile_version.organization_id', 'privacy_profile_version.id'], name='fk_report_privacy_profile_version_id'),
    sa.ForeignKeyConstraint(['organization_id', 'questionnaire_version_id'], ['questionnaire_version.organization_id', 'questionnaire_version.id'], name='fk_report_questionnaire_version_id'),
    sa.ForeignKeyConstraint(['organization_id', 'reporter_key_id'], ['reporter_key.organization_id', 'reporter_key.id'], name='fk_report_reporter_key_id'),
    sa.ForeignKeyConstraint(['organization_id', 'supersedes_report_id'], ['report.organization_id', 'report.id'], name='fk_report_supersedes_report_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_report_org_id')
    )
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.create_index('ix_report_org_area_time', ['organization_id', 'area_id', 'submitted_at'], unique=False)
        batch_op.create_index('ix_report_org_reporter', ['organization_id', 'reporter_key_id', 'submitted_at'], unique=False)
        batch_op.create_index('ix_report_org_status', ['organization_id', 'status'], unique=False)
        batch_op.create_index('uq_report_supersedes', ['organization_id', 'supersedes_report_id'], unique=True)

    op.create_table('broadcast_delivery',
    sa.Column('broadcast_id', sa.String(length=36), nullable=False),
    sa.Column('queued_count', sa.Integer(), nullable=False),
    sa.Column('delivered_count', sa.Integer(), nullable=False),
    sa.Column('blocked_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('queued_count >= 0 AND delivered_count >= 0 AND blocked_count >= 0 AND failed_count >= 0', name='ck_broadcast_delivery_counts'),
    sa.ForeignKeyConstraint(['organization_id', 'broadcast_id'], ['broadcast.organization_id', 'broadcast.id'], name='fk_broadcast_delivery_broadcast_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_broadcast_delivery_org_id')
    )
    op.create_table('need',
    sa.Column('report_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=True),
    sa.Column('reporter_key_id', sa.String(length=36), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('people_affected', sa.Integer(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('unit', sa.String(length=16), nullable=True),
    sa.Column('remaining_supply', sa.String(length=16), nullable=False),
    sa.Column('stated_urgency', sa.String(length=16), nullable=False),
    sa.Column('urgency_inputs', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('access_flags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('encrypted_access_notes', sa.LargeBinary(), nullable=True),
    sa.Column('preferred_times', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('refresh_prompt_count', sa.Integer(), nullable=False),
    sa.Column('last_refresh_prompt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('supersedes_need_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('water_drinking', 'water_other', 'charging')", name='ck_need_category'),
    sa.CheckConstraint("remaining_supply IN ('none', 'little', 'some', 'unknown')", name='ck_need_remaining_supply'),
    sa.CheckConstraint("stated_urgency IN ('today', 'this_week', 'can_wait', 'unknown')", name='ck_need_stated_urgency'),
    sa.CheckConstraint("status IN ('active', 'stale', 'resolved_by_reporter', 'withdrawn', 'expired')", name='ck_need_status'),
    sa.CheckConstraint("unit IS NULL OR (unit = 'liters' AND category IN ('water_drinking', 'water_other')) OR (unit = 'devices' AND category = 'charging')", name='ck_need_unit_matches_category'),
    sa.CheckConstraint("unit IS NULL OR unit IN ('liters', 'devices')", name='ck_need_unit'),
    sa.CheckConstraint('people_affected IS NULL OR people_affected >= 0', name='ck_need_people'),
    sa.CheckConstraint('quantity IS NULL OR (quantity >= 0 AND unit IS NOT NULL)', name='ck_need_quantity'),
    sa.CheckConstraint('refresh_prompt_count >= 0', name='ck_need_refresh_count'),
    sa.CheckConstraint('supersedes_need_id IS NULL OR supersedes_need_id <> id', name='ck_need_no_self_supersede'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_need_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'report_id'], ['report.organization_id', 'report.id'], name='fk_need_report_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'reporter_key_id'], ['reporter_key.organization_id', 'reporter_key.id'], name='fk_need_reporter_key_id'),
    sa.ForeignKeyConstraint(['organization_id', 'supersedes_need_id'], ['need.organization_id', 'need.id'], name='fk_need_supersedes_need_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_need_org_id')
    )
    with op.batch_alter_table('need', schema=None) as batch_op:
        batch_op.create_index('ix_need_org_area_status', ['organization_id', 'area_id', 'category', 'status'], unique=False)
        batch_op.create_index('ix_need_org_reporter', ['organization_id', 'reporter_key_id', 'status'], unique=False)
        batch_op.create_index('ix_need_report', ['organization_id', 'report_id'], unique=False)

    op.create_table('observation',
    sa.Column('report_id', sa.String(length=36), nullable=False),
    sa.Column('area_id', sa.String(length=36), nullable=True),
    sa.Column('outage_episode_id', sa.String(length=36), nullable=True),
    sa.Column('service_type', sa.String(length=32), nullable=False),
    sa.Column('subject_scope', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('observation_start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('observation_end_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('time_precision', sa.String(length=16), nullable=False),
    sa.Column('reported_timezone', sa.String(length=64), nullable=False),
    sa.Column('outage_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('onset_precision', sa.String(length=16), nullable=True),
    sa.Column('source_kind', sa.String(length=32), nullable=False),
    sa.Column('source_group_id', sa.String(length=36), nullable=True),
    sa.Column('supersedes_observation_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("onset_precision IS NULL OR onset_precision IN ('exact', 'hour', 'part_of_day', 'day', 'unknown')", name='ck_observation_onset_precision'),
    sa.CheckConstraint("service_type IN ('electricity', 'piped_water')", name='ck_observation_service_type'),
    sa.CheckConstraint("source_kind IN ('firsthand', 'secondhand', 'forwarded', 'volunteer_observed')", name='ck_observation_source_kind'),
    sa.CheckConstraint("status IN ('available', 'unavailable', 'intermittent', 'unknown')", name='ck_observation_status'),
    sa.CheckConstraint("subject_scope IN ('household', 'area')", name='ck_observation_subject_scope'),
    sa.CheckConstraint("time_precision IN ('exact', 'hour', 'part_of_day', 'day', 'unknown')", name='ck_observation_time_precision'),
    sa.CheckConstraint('observation_start_at IS NULL OR observation_end_at IS NULL OR observation_start_at <= observation_end_at', name='ck_observation_range'),
    sa.CheckConstraint('supersedes_observation_id IS NULL OR supersedes_observation_id <> id', name='ck_observation_no_self_supersede'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_observation_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'outage_episode_id'], ['outage_episode.organization_id', 'outage_episode.id'], name='fk_observation_outage_episode_id'),
    sa.ForeignKeyConstraint(['organization_id', 'report_id'], ['report.organization_id', 'report.id'], name='fk_observation_report_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'supersedes_observation_id'], ['observation.organization_id', 'observation.id'], name='fk_observation_supersedes_observation_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_observation_org_id')
    )
    with op.batch_alter_table('observation', schema=None) as batch_op:
        batch_op.create_index('ix_observation_org_area', ['organization_id', 'area_id', 'service_type'], unique=False)
        batch_op.create_index('ix_observation_org_time_service', ['organization_id', 'observed_at', 'service_type'], unique=False)
        batch_op.create_index('ix_observation_report', ['organization_id', 'report_id'], unique=False)

    op.create_table('report_location',
    sa.Column('report_id', sa.String(length=36), nullable=False),
    sa.Column('encrypted_address', sa.LargeBinary(), nullable=True),
    sa.Column('encrypted_landmark', sa.LargeBinary(), nullable=True),
    sa.Column('restricted_point', _geom('POINT', pg), nullable=True),
    sa.Column('accuracy_meters', sa.Integer(), nullable=True),
    sa.Column('precision', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('accuracy_meters IS NULL OR accuracy_meters >= 0', name='ck_report_location_accuracy'),
    sa.ForeignKeyConstraint(['organization_id', 'report_id'], ['report.organization_id', 'report.id'], name='fk_report_location_report_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_report_location_org_id'),
    sa.UniqueConstraint('report_id', name='uq_report_location_report')
    )
    op.create_table('share_event',
    sa.Column('provider_organization_id', sa.String(length=36), nullable=False),
    sa.Column('actor_ref', sa.String(length=80), nullable=False),
    sa.Column('reporter_key_id', sa.String(length=36), nullable=False),
    sa.Column('fields_shared', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('export_record_id', sa.String(length=36), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id', 'export_record_id'], ['export_record.organization_id', 'export_record.id'], name='fk_share_event_export_record_id'),
    sa.ForeignKeyConstraint(['organization_id', 'provider_organization_id'], ['provider_organization.organization_id', 'provider_organization.id'], name='fk_share_event_provider_organization_id'),
    sa.ForeignKeyConstraint(['organization_id', 'reporter_key_id'], ['reporter_key.organization_id', 'reporter_key.id'], name='fk_share_event_reporter_key_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_share_event_org_id')
    )
    with op.batch_alter_table('share_event', schema=None) as batch_op:
        batch_op.create_index('ix_share_event_provider', ['organization_id', 'provider_organization_id', 'occurred_at'], unique=False)
        batch_op.create_index('ix_share_event_reporter', ['organization_id', 'reporter_key_id', 'occurred_at'], unique=False)

    op.create_table('charging_device_request',
    sa.Column('need_id', sa.String(length=36), nullable=False),
    sa.Column('device_type', sa.String(length=32), nullable=False),
    sa.Column('device_count', sa.Integer(), nullable=False),
    sa.Column('connector_type', sa.String(length=32), nullable=True),
    sa.Column('has_charger', sa.Boolean(), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("device_type IN ('phone', 'medical_device', 'lamp', 'power_bank', 'laptop', 'other')", name='ck_charging_device_request_device_type'),
    sa.CheckConstraint('device_count > 0', name='ck_charging_device_count'),
    sa.ForeignKeyConstraint(['organization_id', 'need_id'], ['need.organization_id', 'need.id'], name='fk_charging_device_request_need_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_charging_device_request_org_id')
    )
    op.create_table('charging_need_detail',
    sa.Column('need_id', sa.String(length=36), nullable=False),
    sa.Column('can_reach_site', sa.Boolean(), nullable=True),
    sa.Column('access_assistance_needed', sa.Boolean(), nullable=True),
    sa.Column('preferred_window_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('preferred_window_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('preferred_window_start IS NULL OR preferred_window_end IS NULL OR preferred_window_start <= preferred_window_end', name='ck_charging_detail_window'),
    sa.ForeignKeyConstraint(['organization_id', 'need_id'], ['need.organization_id', 'need.id'], name='fk_charging_need_detail_need_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('need_id', name='uq_charging_need_detail_need'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_charging_need_detail_org_id')
    )
    op.create_table('observation_link',
    sa.Column('observation_a_id', sa.String(length=36), nullable=False),
    sa.Column('observation_b_id', sa.String(length=36), nullable=False),
    sa.Column('relation', sa.String(length=32), nullable=False),
    sa.Column('rule_version', sa.String(length=32), nullable=False),
    sa.Column('reasons_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_by_membership_id', sa.String(length=36), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("relation IN ('duplicate_of', 'same_source', 'conflicts_with', 'corroborates')", name='ck_observation_link_relation'),
    sa.CheckConstraint('observation_a_id < observation_b_id', name='ck_observation_link_order'),
    sa.ForeignKeyConstraint(['organization_id', 'created_by_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_observation_link_created_by_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'observation_a_id'], ['observation.organization_id', 'observation.id'], name='fk_observation_link_observation_a_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id', 'observation_b_id'], ['observation.organization_id', 'observation.id'], name='fk_observation_link_observation_b_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_observation_link_org_id'),
    sa.UniqueConstraint('organization_id', 'observation_a_id', 'observation_b_id', 'relation', name='uq_observation_link')
    )
    op.create_table('review_task',
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('report_id', sa.String(length=36), nullable=True),
    sa.Column('observation_id', sa.String(length=36), nullable=True),
    sa.Column('need_id', sa.String(length=36), nullable=True),
    sa.Column('area_id', sa.String(length=36), nullable=True),
    sa.Column('duplicate_candidate_id', sa.String(length=36), nullable=True),
    sa.Column('rule_version', sa.String(length=32), nullable=True),
    sa.Column('reasons_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('assigned_membership_id', sa.String(length=36), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reason IN ('duplicate_candidate', 'conflicting_observations', 'unresolved_location', 'flood_or_burst', 'outlier_cell', 'urgent_flag', 'unparsed_text')", name='ck_review_task_reason'),
    sa.CheckConstraint("status IN ('open', 'in_review', 'resolved', 'dismissed')", name='ck_review_task_status'),
    sa.CheckConstraint('report_id IS NOT NULL OR observation_id IS NOT NULL OR need_id IS NOT NULL OR area_id IS NOT NULL OR duplicate_candidate_id IS NOT NULL', name='ck_review_task_target'),
    sa.ForeignKeyConstraint(['organization_id', 'area_id'], ['area.organization_id', 'area.id'], name='fk_review_task_area_id'),
    sa.ForeignKeyConstraint(['organization_id', 'assigned_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_review_task_assigned_membership_id'),
    sa.ForeignKeyConstraint(['organization_id', 'duplicate_candidate_id'], ['duplicate_candidate.organization_id', 'duplicate_candidate.id'], name='fk_review_task_duplicate_candidate_id'),
    sa.ForeignKeyConstraint(['organization_id', 'need_id'], ['need.organization_id', 'need.id'], name='fk_review_task_need_id'),
    sa.ForeignKeyConstraint(['organization_id', 'observation_id'], ['observation.organization_id', 'observation.id'], name='fk_review_task_observation_id'),
    sa.ForeignKeyConstraint(['organization_id', 'report_id'], ['report.organization_id', 'report.id'], name='fk_review_task_report_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_review_task_org_id')
    )
    with op.batch_alter_table('review_task', schema=None) as batch_op:
        batch_op.create_index('ix_review_task_queue', ['organization_id', 'status', 'assigned_membership_id'], unique=False)

    op.create_table('water_need_detail',
    sa.Column('need_id', sa.String(length=36), nullable=False),
    sa.Column('intended_use', sa.String(length=32), nullable=True),
    sa.Column('people_to_serve', sa.Integer(), nullable=True),
    sa.Column('remaining_supply_hours', sa.Integer(), nullable=True),
    sa.Column('has_containers', sa.Boolean(), nullable=True),
    sa.Column('container_capacity_liters', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('receiving_assistance_needed', sa.Boolean(), nullable=True),
    sa.Column('preferred_window_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('preferred_window_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('quantity_estimation_basis', sa.String(length=32), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('container_capacity_liters IS NULL OR container_capacity_liters >= 0', name='ck_water_detail_capacity'),
    sa.CheckConstraint('people_to_serve IS NULL OR people_to_serve >= 0', name='ck_water_detail_people'),
    sa.CheckConstraint('preferred_window_start IS NULL OR preferred_window_end IS NULL OR preferred_window_start <= preferred_window_end', name='ck_water_detail_window'),
    sa.CheckConstraint('remaining_supply_hours IS NULL OR remaining_supply_hours >= 0', name='ck_water_detail_hours'),
    sa.ForeignKeyConstraint(['organization_id', 'need_id'], ['need.organization_id', 'need.id'], name='fk_water_need_detail_need_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('need_id', name='uq_water_need_detail_need'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_water_need_detail_org_id')
    )
    op.create_table('review_decision',
    sa.Column('review_task_id', sa.String(length=36), nullable=False),
    sa.Column('disposition', sa.String(length=32), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('reviewer_membership_id', sa.String(length=36), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('review_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("disposition IN ('valid', 'duplicate', 'spam', 'location_corrected', 'unresolved')", name='ck_review_decision_disposition'),
    sa.ForeignKeyConstraint(['organization_id', 'review_task_id'], ['review_task.organization_id', 'review_task.id'], name='fk_review_decision_review_task_id'),
    sa.ForeignKeyConstraint(['organization_id', 'reviewer_membership_id'], ['organization_membership.organization_id', 'organization_membership.id'], name='fk_review_decision_reviewer_membership_id'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'id', name='uq_review_decision_org_id')
    )

    # Membership -> provider organization (cycle-breaking FK added last).
    with op.batch_alter_table('organization_membership', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_organization_membership_provider_organization_id', 'provider_organization', ['organization_id', 'provider_organization_id'], ['organization_id', 'id'], use_alter=True)

    if pg:
        _install_postgres_objects()


def downgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    if pg:
        _drop_postgres_objects_before_tables()
    with op.batch_alter_table('organization_membership', schema=None) as batch_op:
        batch_op.drop_constraint('fk_organization_membership_provider_organization_id', type_='foreignkey')

    with op.batch_alter_table('inbound_event', schema=None) as batch_op:
        batch_op.drop_index('ix_inbound_event_pending')
        batch_op.drop_column('retention_until')
        batch_op.drop_column('last_error')
        batch_op.drop_column('attempts')
        batch_op.drop_column('status')
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('idempotency_key', schema=None) as batch_op:
        batch_op.drop_constraint('uq_idempotency', type_='unique')
        batch_op.create_unique_constraint(batch_op.f('uq_idempotency'), ['organization_id', 'endpoint', 'key'])
        batch_op.drop_column('expires_at')
        batch_op.drop_column('request_digest')
        batch_op.drop_column('actor_scope')

    op.drop_table('review_decision')
    op.drop_table('water_need_detail')
    with op.batch_alter_table('review_task', schema=None) as batch_op:
        batch_op.drop_index('ix_review_task_queue')

    op.drop_table('review_task')
    op.drop_table('observation_link')
    op.drop_table('charging_need_detail')
    op.drop_table('charging_device_request')
    with op.batch_alter_table('share_event', schema=None) as batch_op:
        batch_op.drop_index('ix_share_event_reporter')
        batch_op.drop_index('ix_share_event_provider')

    op.drop_table('share_event')
    op.drop_table('report_location')
    with op.batch_alter_table('observation', schema=None) as batch_op:
        batch_op.drop_index('ix_observation_report')
        batch_op.drop_index('ix_observation_org_time_service')
        batch_op.drop_index('ix_observation_org_area')

    op.drop_table('observation')
    with op.batch_alter_table('need', schema=None) as batch_op:
        batch_op.drop_index('ix_need_report')
        batch_op.drop_index('ix_need_org_reporter')
        batch_op.drop_index('ix_need_org_area_status')

    op.drop_table('need')
    op.drop_table('broadcast_delivery')
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_index('uq_report_supersedes')
        batch_op.drop_index('ix_report_org_status')
        batch_op.drop_index('ix_report_org_reporter')
        batch_op.drop_index('ix_report_org_area_time')

    op.drop_table('report')
    with op.batch_alter_table('outbox_message', schema=None) as batch_op:
        batch_op.drop_index('ix_outbox_pending')

    op.drop_table('outbox_message')
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index('ix_message_conversation')

    op.drop_table('message')
    op.drop_table('export_record')
    op.drop_table('broadcast')
    with op.batch_alter_table('activity_area', schema=None) as batch_op:
        batch_op.drop_index('ix_activity_area_area')

    op.drop_table('activity_area')
    op.drop_table('provider_scope')
    with op.batch_alter_table('permission', schema=None) as batch_op:
        batch_op.drop_index('ix_permission_subject')
        batch_op.drop_index('ix_permission_endpoint')

    op.drop_table('permission')
    with op.batch_alter_table('indicator_cell', schema=None) as batch_op:
        batch_op.drop_index('ix_indicator_cell_lookup')

    op.drop_table('indicator_cell')
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index('ix_conversation_endpoint')

    op.drop_table('conversation')
    with op.batch_alter_table('campaign_area', schema=None) as batch_op:
        batch_op.drop_index('uq_campaign_area')

    op.drop_table('campaign_area')
    op.drop_table('api_key')
    op.drop_table('alert_subscription_area')
    op.drop_table('alert_delivery')
    with op.batch_alter_table('activity', schema=None) as batch_op:
        batch_op.drop_index('ix_activity_provider')
        batch_op.drop_index('ix_activity_org_status')

    op.drop_table('activity')
    with op.batch_alter_table('reporter_key', schema=None) as batch_op:
        batch_op.drop_index('ix_reporter_key_endpoint')

    op.drop_table('reporter_key')
    op.drop_table('public_indicator_cell')
    op.drop_table('public_activity')
    op.drop_table('provider_organization')
    with op.batch_alter_table('privacy_profile_version', schema=None) as batch_op:
        batch_op.drop_index('uq_privacy_profile_version')
        batch_op.drop_index('uq_privacy_profile_active', postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))

    op.drop_table('privacy_profile_version')
    op.drop_table('outage_episode')
    op.drop_table('merge_event')
    with op.batch_alter_table('meeting_point', schema=None) as batch_op:
        batch_op.drop_index('ix_meeting_point_org_area')

    op.drop_table('meeting_point')
    op.drop_table('indicator_dirty_cell')
    with op.batch_alter_table('external_indicator', schema=None) as batch_op:
        batch_op.drop_index('ix_external_indicator_lookup')

    op.drop_table('external_indicator')
    op.drop_table('duplicate_candidate')
    op.drop_table('data_job_result')
    op.drop_table('coverage_cell')
    op.drop_table('campaign')
    with op.batch_alter_table('area_boundary', schema=None) as batch_op:
        batch_op.drop_index('uq_area_boundary_version')

    op.drop_table('area_boundary')
    with op.batch_alter_table('area_alias', schema=None) as batch_op:
        batch_op.drop_index('uq_area_alias')

    op.drop_table('area_alias')
    op.drop_table('alert_subscription')
    with op.batch_alter_table('questionnaire_version', schema=None) as batch_op:
        batch_op.drop_index('uq_questionnaire_version')

    op.drop_table('questionnaire_version')
    with op.batch_alter_table('policy_version', schema=None) as batch_op:
        batch_op.drop_index('uq_policy_version')

    op.drop_table('policy_version')
    with op.batch_alter_table('data_job', schema=None) as batch_op:
        batch_op.drop_index('ix_data_job_claim')

    op.drop_table('data_job')
    op.drop_table('contact_endpoint')
    with op.batch_alter_table('audit_event', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_event_org_time')
        batch_op.drop_index('ix_audit_event_entity')

    op.drop_table('audit_event')
    with op.batch_alter_table('area', schema=None) as batch_op:
        batch_op.drop_index('uq_area_code')
        batch_op.drop_index('ix_area_org_parent')

    op.drop_table('area')
    op.drop_table('message_status_event')
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_index('ix_job_claim')

    op.drop_table('job')

    with op.batch_alter_table('organization_membership', schema=None) as batch_op:
        batch_op.drop_constraint('uq_organization_membership_org_id', type_='unique')
        batch_op.drop_column('provider_organization_id')

    with op.batch_alter_table('household', schema=None) as batch_op:
        batch_op.drop_constraint('uq_household_org_id', type_='unique')

    if pg:
        _drop_postgres_functions()
    _restore_legacy_tables(pg)
