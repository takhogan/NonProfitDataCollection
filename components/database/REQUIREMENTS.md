# Database requirements

PostgreSQL/PostGIS schema, tenant isolation, integrity, and lifecycle. These requirements
enforce in storage what [domain](../domain/REQUIREMENTS.md) defines. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Tenant isolation

- **DB-001 (P0) Organization ownership.** Every operational table has a non-null
  `organization_id`, and every relationship between operational records uses an
  organization-scoped composite foreign key.
  - *Accept:* inserting a need that references another org's case fails at the database.
- **DB-002 (P0) Row-level security.**
  - RLS is enabled and forced on all tenant tables, for reads and writes.
  - Runtime roles cannot bypass RLS.
  - Tenant and actor are set transaction-locally (`set_config(..., true)`).
  - A query with no tenant set returns no rows.
- **DB-003 (P0) Role-aware policies.**
  - Partner users can read only:
    - the aggregate views
    - a `partner_contactable_list` view, filtered in SQL by the rules in `DOM-075`
      (vetted status, scope, consent, safe-to-contact, shareable, open)
  - Analyst access is limited to aggregate views.
  - Policies, not only API code, enforce this (defense in depth for SEC-08).
  - *Accept:* a partner database session cannot select from `household`, `contact`,
    `observation`, or `review_*` tables.
- **DB-004 (P0) Separate roles.** Migration, runtime API, runtime worker, read-only
  analytics, and backup roles each have least privilege. Queue (pg-boss) access does not
  grant tenant data access.
- **DB-005 (P0) Isolation test suite.** Seeds include two organizations. CI asserts
  denial across orgs for every table, view, read model, export query, and job handler.

## Schema stages

- **DB-010 (P0) Stage 1.** Organizations, users, local credentials (Argon2id hash, TOTP
  secret encrypted), memberships, areas, locations, households, persons, contacts,
  permissions (including sharing consent), campaigns, questionnaires, assessments,
  observations, cases, needs, need details, policies, and audit events.
- **DB-011 (P0) Stage 2: sharing.**
  - Partner organizations, with vetting status, responsible contact, statement version,
    and per-partner flags.
  - Partner scopes (areas × categories), need sharing attributes, and share events.
  - Export records: requester, partner, scope, row count, watermark ID, expiry, and
    file reference.
  - Partner outcomes (P1).
  - Service directory points (P1).
- **DB-015 (P2) Fulfillment tables.** Resource offers, water supply, allocations, runs and
  stops, deliveries, charging sites, slots, bookings, and sessions, per PLATFORM_PLAN.md,
  only if `DOM-090` is reinstated.
- **DB-012 (P0) Stage 3.** Conversations, messages, provider status events, inbox,
  outbox, and the idempotency (operation key) store.
- **DB-013 (P0) Stage 4.**
  - Observation links, review tasks/decisions/evidence, and duplicate candidates.
  - Merge events, data jobs/results, external indicators, and aggregate read models.
- **DB-014 (P2) Stage 5.** Sharing agreements, referrals, and sharing access events.

## Integrity constraints

- **DB-020 (P0) Units and quantities.**
  - The unit is constrained by need category: liters or people for the `water_*`
    categories, devices for `charging`.
  - Requested quantities are ≥ 0 or null. Partner-reported quantities are > 0 or null.
  - Water is stored as `numeric(12,3)` liters, never as floats.
- **DB-021 (P0) Time ranges.** `start <= end` wherever both exist.
- **DB-022 (P0) Status enums.** Statuses are constrained to known values. Transition
  legality lives in the domain. Share events, export records, and partner outcomes are
  append-only for runtime roles.
- **DB-023 (P0) Service detail.** Each need has exactly one matching detail row for its
  category. This is enforced by deferred constraint triggers.
- **DB-024 (P0) Links.**
  - No self-links.
  - A unique unordered pair per relation for observation links and duplicate
    candidates.
  - A review task has at least one typed target.
- **DB-025 (P0) Provider uniqueness.**
  - Inbound `provider_message_id` is unique per channel account.
  - Status events are deduplicated by (provider message ID, status, provider
    timestamp).

## Concurrency and idempotency

- **DB-030 (P2) Reservation locking.** Only needed with `DB-015`.
  - Allocation and booking lock the supply/slot row and re-check capacity in the same
    transaction.
  - *Accept:* 50 concurrent bookings against a slot of capacity 4 yield exactly 4
    bookings.
- **DB-034 (P0) Consistent exports.** An export reads the contactable list in a single
  repeatable-read snapshot and writes its share events in the same transaction. The
  file therefore matches exactly what was logged as shared.
- **DB-031 (P0) Operation keys.**
  - The table is unique on (organization, actor scope, operation type, key).
  - It stores a request digest and result reference, and keeps them for at least 30
    days.
- **DB-032 (P0) Optimistic versions.** Editable records (household, need, case,
  site) carry a `version` integer. A stale update fails with a conflict.
- **DB-033 (P0) Short transactions.** No transaction is held open across network calls.
  A statement timeout and an idle-in-transaction timeout are configured.

## Inbox, outbox, and jobs

- **DB-040 (P0) Inbox.**
  - The inbox records the accepted provider event: channel account, provider event ID,
    received time, processing status, attempts, last error class, and a restricted
    payload reference.
  - Raw payloads are kept per NFR-09.
- **DB-041 (P0) Outbox.**
  - The outbox records the message intent: purpose, template/reply, conversation,
    status, attempts, provider message ID, and send-outcome uncertainty.
  - It is written in the same transaction as the domain change.
- **DB-042 (P0) Data jobs.** Data-job and data-job-result tables follow
  [data-jobs.md](../contracts/data-jobs.md). Lease tokens are stored hashed, and fencing
  is done by attempt number.
- **DB-043 (P0) Backlog views.** Views expose pending inbox count/age, outbox count/age,
  failed jobs, and data job lag, for monitoring and staff status (NFR-10).

## Sensitive data protection

- **DB-050 (P0) Field encryption.**
  - Contact addresses, landmark descriptions, precise points, names, and free-text
    notes are encrypted at the application level with keys from a managed key service
    (SEC-04).
  - Database dumps never contain those values in plaintext.
- **DB-051 (P0) Lookup HMAC.** Contact lookup uses an org-scoped HMAC with a protected
  key. Plain phone hashes are never used.
- **DB-052 (P0) Precise point isolation.** Precise points are stored in a separate
  restricted table. Aggregate read models reference only `area_id`.
- **DB-053 (P0) Audit table.**
  - Audit events are append-only: no updates or deletes for runtime roles.
  - They carry request IDs and redacted summaries, and contain no raw PII.
- **DB-054 (P1) Key rotation.** Re-encryption of contact and location fields can run
  online. A rotation runbook is tested in staging (SEC-14).

## Geography

- **DB-060 (P0) Area hierarchy.**
  - Areas are typed state → municipality → parish → sector, with versioned boundaries,
    source, and official code when available.
  - Aliases support local names.
  - Seeds include the Caracas metro pilot parishes (D5). Synthetic sector polygons are
    used until real ones are agreed.
- **DB-061 (P0) Spatial indexes.** GiST indexes on area boundaries and restricted points.
  Point-in-area resolution is available as a function.
- **DB-062 (P1) Service zones.** Optional zones by service type (e.g., Hidrocapital
  sector, feeder) carry provenance. Zone membership never overrides area.

## Retention and lifecycle

- **DB-070 (P0) Retention metadata.**
  - Records subject to retention carry `retention_until`, or derive it from policy.
  - A retention job anonymizes or deletes per NFR-09 and records counts in the audit
    log.
- **DB-071 (P0) Anonymization.** Anonymizing a household removes contacts, names,
  landmarks, and points. It keeps area, counts, quantities, and timestamps, so
  aggregate history stays valid.
- **DB-072 (P1) Emergency purge.** A function purges contact endpoints and precise
  locations by area or campaign, behind a two-admin approval record (SEC-15).

## Read models

- **DB-075 (P0) Aggregate views.**
  - Area × service × time-bucket views of observations: status counts, distinct
    households, freshness (last observation time), and unknown share.
  - Need backlogs by unit and fulfillment totals.
  - Views are derived from source tables, never written independently.
- **DB-076 (P0) Suppression in SQL.** Aggregate views used by analysts and maps apply
  small-cell suppression (SEC-10) in the view, not just in the UI.

## Media and artifacts

- **DB-080 (P1) Object references.** Media (voice notes) and data-worker artifacts are
  stored in restricted object storage. The database keeps a reference, checksum, size,
  content type, retention date, and owning org.

## Seeds, migrations, and operations

- **DB-090 (P0) Synthetic seeds.** Seeds contain:
  - two orgs, and every role in the [roles table](../REQUIREMENTS.md#roles)
  - three partner organizations (vetted water, vetted charging, unvetted)
  - synthetic Libertador parishes and sectors
  - 50 synthetic households, with:
    - two that share a phone
    - a mix of consented and non-consented sharing
    - one that is not safe to contact
  - mock Monitor Ciudad indicators
- **DB-091 (P0) Migrations.**
  - Migrations are forward-only and run once per release by the migration role.
  - They are tested from an empty database and from the previous release.
  - No release requires dropping a populated column during rollback.
- **DB-100 (P0) Backups.**
  - Automated encrypted backups and point-in-time recovery, hosted outside Venezuela.
  - Restore is tested before launch and quarterly (NFR-08).
  - Backup retention is aligned with NFR-09: after the backup window, deleted data
    ages out of backups.
