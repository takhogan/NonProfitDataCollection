# Database and persistence

PostgreSQL with PostGIS is the proposed persistence layer. This component will own
versioned migrations, transaction/repository implementations, indexes, access
policies, and synthetic seeds. No executable migrations exist yet.

Implement the logical model from [PLATFORM_PLAN.md](../../PLATFORM_PLAN.md) in stages:

1. Organizations and memberships; privacy profiles; areas and meeting points; reports,
   observations, and needs; reporter keys and permissions; audit.
2. Indicator and coverage cells; provider organizations, activities, alerts, API keys,
   share events, and export records.
3. Conversations and messages; inbox, outbox, and jobs; broadcasts.
4. Review and evidence; data jobs and results with fenced leases; public snapshots.
   Household records, cases, and sharing agreements are optional or later
   (`DB-015`).

Data jobs and results are application-owned tables, separate from the operational
worker's job tables. The data worker reaches them only through the scoped internal API,
without database credentials.

Audit fields, organization ownership, and permission enforcement belong in the
first stage even when their richer UI arrives later. Any live contact collection
requires the relevant permission records; synthetic fixtures do not authorize it.

Use organization-scoped foreign keys, server authorization, and row access policies.
Application roles must not bypass tenant isolation. Workers must set transaction-local
organization context explicitly. Separate sensitive contacts/locations from aggregate
read models, and avoid personal information in logs or audit summaries.

Enforce units, non-negative quantities, valid time intervals, provider event
uniqueness, and operation idempotency. Write exports and share events atomically.
Do not hold a database transaction open while calling WhatsApp.

First deliverable: repeatable local migrations and synthetic fixtures for two
organizations, including a negative cross-organization access test.

## Tech stack and hosting

The stack was decided on 7 November 2026: Python, following the first implementation.

- PostgreSQL + PostGIS, on managed Render Postgres for the proposed pilot.
- SQLAlchemy 2.0 models and sessions with psycopg 3. GeoAlchemy2 handles spatial
  columns.
- Alembic migrations (the first already exists in `whatsapp/api/migrations`). Use
  `op.execute` SQL for row-level security policies, exclusion and deferred
  constraints, triggers, and spatial indexes that the ORM does not express.
- Docker Compose PostgreSQL/PostGIS for development, and a real isolated PostgreSQL
  for CI integration tests.
- SQLite is allowed only for quick local demos. Tenant policies, `SKIP LOCKED` job
  claims, and spatial behavior must be tested on PostgreSQL.
- The application owns all tables, including operational job, inbox/outbox, and
  data-job tables. There is no third-party queue schema.

Use the ORM for ordinary reads and writes. Drop to explicit SQL where tenant policies,
spatial predicates, or row locks need direct control.

## Planned modules and storage boundaries

These are modules in the backend package (currently `whatsapp/api`):

- `app/models`
- `app/db.py` (engine, sessions, and the tenant transaction helper)
- `app/read_models`
- `migrations/`
- `scripts/seed.py`
- `tests/` (PostgreSQL integration tests) Store media and raster outputs in restricted object
storage and keep references/checksums in PostgreSQL. The object-store provider remains
open pending region, access, and cost review; local fixtures can use a development store.

The transaction helper opens one session and begins a transaction. It sets
tenant/actor context transaction-locally (`SET LOCAL` / `set_config(..., true)`),
invokes the work, and commits or rolls back before closing.
Use separate runtime and migration roles, ensure runtime roles cannot bypass RLS,
and apply appropriate policies to both reads and writes. All transaction statements
must use the same session. Job-table access does not imply permission to read tenant
data.

## Capacity and lifecycle

Enforce provider, analyst, and public visibility in row policies as well as in the API.
Enforce unique operation keys and tenant-scoped foreign keys in the database.
Use spatial indexes for candidate matching and ordinary indexes for organization,
status, assignee, and observation time. Avoid storing arbitrary large JSON blobs in
hot queue tables. Define job/audit retention separately from household record retention.

Provision automated backups and test restoration before pilot launch. Document
actual backup retention, recovery objectives, pool budgets, and alert thresholds
when a hosting tier is selected. Validate migrations from an empty database and the
previous schema; deployment rollback must not require dropping populated columns.

References: [SQLAlchemy 2.0 sessions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html), [Alembic](https://alembic.sqlalchemy.org/).
