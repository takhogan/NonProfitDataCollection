# Database requirements

PostgreSQL/PostGIS schema, tenant isolation, privacy-profile enforcement, indicators,
and lifecycle. Uses SQLAlchemy 2.0 and Alembic (D19). Enforces in storage what
[domain](../domain/REQUIREMENTS.md) defines. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Tenant isolation

- **DB-001 (P0) Ownership.**
  - Every operational table has a non-null `organization_id`.
  - Relationships use org-scoped composite foreign keys.
  - *Accept:* a report cannot reference another org's area overlay, meeting point, or
    campaign.
- **DB-002 (P0) Row-level security.**
  - Forced on all tenant tables, for reads and writes.
  - Tenant and actor are set transaction-locally.
  - Runtime roles cannot bypass it.
  - No tenant set means no rows.
- **DB-003 (P0) Role-aware policies.**
  - Provider sessions and API keys read only indicator, coverage, and activity views.
    Vetted ones also read the `provider_contact_list` view, filtered in SQL by
    `DOM-054`.
  - Analysts read only aggregate views.
  - The public role reads only the `public_*` snapshot tables.
  - *Accept:* a provider session cannot select from `report`, `contact_endpoint`,
    `permission`, or `review_*`.
- **DB-004 (P0) Least-privilege roles.** Separate roles for migration, API runtime,
    worker runtime, provider API, public read, analytics, and backup. Access to the job
    tables grants no tenant data.
- **DB-005 (P0) Isolation suite.** CI seeds two orgs (one protective, one standard) and
  asserts isolation across tenants, roles, and profiles. It covers every table, view,
  export query, and job handler.

## Schema

- **DB-010 (P0) Core tables.**
  - Organizations, users, local credentials (Argon2id hash, encrypted TOTP secret),
    memberships, sessions, and audit events.
  - Privacy profile versions and policy versions.
  - Areas with aliases and versioned boundaries; meeting points.
  - Campaigns and questionnaires.
- **DB-011 (P0) Reporting tables.**
  - Contact endpoints (encrypted address, plus an org-scoped HMAC) and pseudonymous
    reporter keys with a rotation epoch.
  - Permissions (purpose-specific), conversations, and messages.
  - Reports (with the profile version), observations, needs, and need details.
  - Location details: meeting point reference, or encrypted address and optional point
    in a separate restricted table.
  - Inbox, outbox, jobs, and the idempotency store.
- **DB-012 (P0) Provider tables.**
  - Provider organizations (vetting, scope, contact, statement version, name-disclosure
    flag) and provider scopes.
  - Activities and activity areas.
  - Alert subscriptions and alert deliveries.
  - API keys (hash, scope, expiry, last used).
  - Share events and export records.
  - Broadcasts and broadcast deliveries (counts only).
- **DB-013 (P0) Aggregation tables.**
  - Indicator cells (area × category/service × bucket), with method, profile version,
    and input watermark.
  - Coverage cells.
  - External indicators.
  - `public_indicator_cell` and `public_activity` snapshots.
- **DB-014 (P0) Quality tables.** Observation links, review tasks and decisions,
  duplicate candidates, merge events, data jobs and results.
- **DB-015 (P2) Optional modules.** Household records (standard profile), and the
  case-management and fulfillment tables (`DOM-090`). Cross-tenant sharing agreements
  (`DOM-095`).

## Integrity

- **DB-020 (P0) Units.** Liters are allowed only for the water categories; devices only
  for `charging`; people counts are ≥ 0 or null. Water uses `numeric(12,3)`, never
  floats.
- **DB-021 (P0) Time ranges.** `start <= end`. Activity schedules are valid.
- **DB-022 (P0) Enumerations.** Statuses, categories, coverage labels, and confidence
  labels are constrained. Share events, export records, alert deliveries, and audit
  are append-only for runtime roles.
- **DB-023 (P0) Profile constraints.**
  - When the report's profile version disallows names, addresses, or points, those
    columns must be null. This is enforced by a trigger reading the profile version.
  - *Accept:* inserting an address on a protective-profile report fails.
- **DB-024 (P0) Links.** No self-links. One unordered pair per relation. A review task
  has at least one typed target.
- **DB-025 (P0) Provider uniqueness.** Inbound provider message IDs are unique per
  channel account. Status events are deduplicated.

## Concurrency and idempotency

- **DB-030 (P0) Idempotency store.** Unique on (org, actor scope, operation, key), with
  the request digest and result, kept ≥ 30 days.
- **DB-031 (P0) Optimistic versions.** Activities, meeting points, providers, and profile
  drafts carry a version. A stale update gives a conflict.
- **DB-032 (P0) Short transactions.** No network calls inside transactions. Statement
  and idle-in-transaction timeouts are set.
- **DB-033 (P0) Consistent exports.** Contact-list exports read a repeatable-read
  snapshot and write their share events in the same transaction.
- **DB-034 (P0) Job claims.** Jobs are claimed with `FOR UPDATE SKIP LOCKED`, with a
  lease expiry, attempt count, and next-run time. Per-conversation serialization uses
  an advisory lock.

## Sensitive data protection

- **DB-050 (P0) Field encryption.** Contact addresses, names, addresses and landmarks,
  points, and free-text notes are encrypted at the application level with
  managed keys. Dumps never contain them in plaintext.
- **DB-051 (P0) Lookup HMAC.** Contact lookup and reporter keys use org-scoped HMAC keys.
  Plain phone hashes are never used.
- **DB-052 (P0) Isolation of precise data.** Addresses and points live in a restricted
  table. Aggregation and provider views reference only `area_id` and meeting points.
- **DB-053 (P0) Audit.** Append-only and redacted, with request IDs.
- **DB-054 (P1) Key rotation.** Online re-encryption, with a tested runbook.

## Geography

- **DB-060 (P0) Areas.** State → municipality → parish → sector, with versioned
  boundaries, sources, codes, and aliases. Seeds include synthetic Libertador parishes.
- **DB-061 (P0) Spatial indexes.** GiST indexes on boundaries and restricted points, and
  point-in-area resolution.
- **DB-062 (P0) Meeting points.** Per sector: name, type, public description, an
  optional public coordinate (a public place, not a home), and active state.
- **DB-063 (P1) Service zones.** Optional zones by service type, with provenance.

## Aggregation

- **DB-070 (P0) Retention.** Per-profile retention runs daily. It anonymizes reports
  after the retention period, deletes contact endpoints and permissions per the
  profile, and records counts in the audit.
- **DB-071 (P0) Anonymization.** Removes contacts, names, addresses, points, notes, and
  reporter keys. Keeps area, category, counts, quantities, and timestamps, so aggregate
  history stays valid.
- **DB-072 (P1) Emergency purge.** Purge by area or campaign, with two-admin approval
  (SEC-15).
- **DB-075 (P0) Indicator maintenance.**
  - Indicator and coverage cells are recomputed from source tables by worker jobs
    (`OPW-045`/`046`), never edited directly.
  - A dirty-cell queue drives incremental recompute.
  - A nightly full rebuild must reproduce the incremental results.
- **DB-076 (P0) Suppression in SQL.** Provider, analyst, API, and public views apply *k*
  suppression in the view or snapshot, not just in the UI.
- **DB-077 (P0) Public snapshots.** Public tables hold only `DOM-080`/`DOM-081` fields.
  They are written by the worker on the delay schedule and truncated when the public
  dashboard is disabled.

## Media and artifacts

- **DB-080 (P1) Object references.** Media and data-worker artifacts are kept in
  restricted object storage. The database stores a reference, checksum, size, type,
  retention date, and owner.

## Seeds, migrations, operations

- **DB-090 (P0) Seeds.** Two orgs (protective and standard profiles), with:
  - every role
  - three providers (two vetted, one unvetted) with activities and alert
    subscriptions
  - synthetic Libertador sectors with meeting points
  - about 300 synthetic reports covering shared phones, repeat reporters, mixed
    permissions, unknown-coverage sectors, and an outage spike
  - mock Monitor Ciudad indicators
- **DB-091 (P0) Migrations.** Alembic migrations, run once per release by the migration
  role. Tested from empty and from the previous release. No release requires dropping a
  populated column. SQL for row-level security, triggers, and spatial indexes goes in
  `op.execute`.
- **DB-092 (P0) PostgreSQL in CI.** Integration tests run on PostgreSQL/PostGIS. SQLite is
  allowed for quick demos only, and tests for row-level security, triggers,
  `SKIP LOCKED`, and spatial behavior are skipped there.
- **DB-100 (P0) Backups.** Encrypted, with point-in-time recovery, outside Venezuela.
  Restores are tested before launch and quarterly. Backup retention is aligned with
  NFR-09.
