# Database and persistence

PostgreSQL with PostGIS is the proposed persistence layer. This component will own
versioned migrations, transaction/repository implementations, indexes, access
policies, and synthetic seeds. No executable migrations exist yet.

Implement the logical model from [PLATFORM_PLAN.md](../../PLATFORM_PLAN.md) in stages:

1. Organizations/memberships; households/contacts; assessments/observations; cases/needs.
2. Partner organizations, scopes, share events, export records, and outcomes
   (fulfillment tables deferred; see REQUIREMENTS.md `DB-015`).
3. Invitations/conversations/messages; inbox/outbox/jobs; permissions and audit history.
4. Review/evidence, data jobs/results with fenced leases and retry metadata,
   aggregate read models, and later sharing/referrals.

Data jobs/results are application-owned tables, separate from pg-boss. Python
accesses them only through the scoped internal API, without database credentials.

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

## Proposed tech stack and hosting

- PostgreSQL + PostGIS, hosted on managed Render Postgres for the proposed pilot.
- TypeScript repository adapters using `node-postgres` (`pg`) and parameterized SQL.
- `node-pg-migrate` as the proposed migration runner, with SQL for constraints,
  policies, spatial operations, and indexes; verify compatible versions at setup.
- Docker Compose PostgreSQL/PostGIS for development and a real isolated database
  for CI integration tests. Do not substitute SQLite for PostgreSQL-specific checks.
- pg-boss owns its queue schema; the application owns its data-job and inbox/outbox tables.

Prefer explicit SQL initially because tenant policies, spatial predicates, and
reservation locks need direct control. Repository interfaces provide the boundary
for application code; adding an ORM is not a prerequisite.

## Planned modules and storage boundaries

`migrations`, `src/pool`, `src/transactions`, `src/repositories`, `src/read-models`,
`seeds`, and `tests/integration`. Store media and raster outputs in restricted object
storage and keep references/checksums in PostgreSQL. The object-store provider remains
open pending region, access, and cost review; local fixtures can use a development store.

The transaction helper acquires one client, begins a transaction, sets tenant/actor
context transaction-locally, invokes work, and commits or rolls back before release.
Use separate runtime and migration roles, ensure runtime roles cannot bypass RLS,
and apply appropriate policies to both reads and writes. All transaction statements
must use the same client. Queue access does not imply permission to read tenant data.

## Capacity and lifecycle

Enforce partner visibility in row policies as well as in the API.
Enforce unique operation keys and tenant-scoped foreign keys in the database.
Use spatial indexes for candidate matching and ordinary indexes for organization,
status, assignee, and observation time. Avoid storing arbitrary large JSON blobs in
hot queue tables. Define job/audit retention separately from household record retention.

Provision automated backups and test restoration before pilot launch. Document
actual backup retention, recovery objectives, pool budgets, and alert thresholds
when a hosting tier is selected. Validate migrations from an empty database and the
previous schema; deployment rollback must not require dropping populated columns.

Reference: [node-postgres transactions](https://node-postgres.com/features/transactions).
