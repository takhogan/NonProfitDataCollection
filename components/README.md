# Component plan

## Architecture

Plan four runnable processes: web, API, operational worker, and Python data worker.
The initial staff workflow does not require deploying the data worker. Domain,
contracts, database, and WhatsApp are shared packages, not separate services.
Dashboards, CRM, analytics, and review are modules within the web/API, rather than
independent applications.

```text
Staff browser → web → api → domain → database → PostgreSQL
                      ↑                 ↑
WhatsApp → webhook in api → durable inbox → operational-worker → domain
                                              ↓
                                 transactional outbox → whatsapp → provider

External sources → data-worker ↔ internal API → data jobs/results in PostgreSQL
                                  ↓
                        operational-worker → evidence review

contracts defines validated boundaries, including cross-language JSON schemas
```

The webhook authenticates provider requests and persists an inbox item before
acknowledging receipt. The operational worker processes inbox items idempotently. Domain
mutations and outbound-message intents commit together; sending occurs afterward.

Proposed production topology: Render API web service, Render Background Worker
(Docker + TypeScript/Node.js + pg-boss), and managed Render Postgres/PostGIS, in the
same region. Start with one operational worker instance and add a separate Python
data worker when external-source processing is implemented. See the
[operational worker deployment plan](operational-worker/README.md)
for local development, queue consistency, release steps, and operational checks.

## Requirements

Feature requirements, priorities (P0 pilot / P1 during pilot / P2 later), and
acceptance criteria live in [REQUIREMENTS.md](REQUIREMENTS.md) and each component's
`REQUIREMENTS.md`. This file covers architecture and stack.

## Component responsibilities

1. **[web](web/README.md):** Staff and partner sign-in, household CRM, intake, case
   queues, handoff inbox, review, aggregate map/dashboards, and the partner portal.
2. **[api](api/README.md):** Authentication, organization authorization, input
   validation, application endpoints, provider webhook handling, and read models.
3. **[operational-worker](operational-worker/README.md):** TypeScript intake
   conversation, retries, outbound messages, resident follow-ups, share notices,
   evidence ingestion, and retention.
4. **[data-worker](data-worker/README.md):** Python source ingestion, geospatial
   processing, quality checks, and provenance-rich evidence candidates.
5. **[domain](domain/README.md):** Case/need lifecycle, urgency, consent and
   permissions, partner sharing rules, follow-ups, and review rules.
6. **[database](database/README.md):** Relational schema, tenant isolation,
   constraints, transaction primitives, migrations, indexes, and synthetic seeds.
7. **[contracts](contracts/README.md):** Runtime-validated API payloads, event
   schemas, intake versions, enumerations, errors, and quantity/time conventions.
8. **[whatsapp](whatsapp/README.md):** Provider-neutral adapter interface, fake
   adapter, and conformance suite. A separate contributor builds the production Meta
   Cloud API adapter against that interface.

## Tech stack by component

The following stack is the proposed implementation baseline, not installed software.
Pin supported, mutually compatible versions during setup and commit both lockfiles.

- **Web:** React, TypeScript, Vite, React Router, TanStack Query, React Hook Form,
  CSS Modules; MapLibre when maps are introduced. Deploy a static build on Render.
- **API:** Node.js LTS, TypeScript, Fastify, Ajv, Pino, and the shared persistence
  package. Deploy as a Dockerized Render Web Service.
- **Operational worker:** Node.js LTS, TypeScript, pg-boss, Pino, and shared domain
  packages. Deploy as a Render Background Worker.
- **Data worker:** Python, uv, HTTPX, jsonschema, pytest, and Ruff; add NumPy/pandas,
  GeoPandas, Rasterio, or Xarray per pipeline. Deploy a separate Docker worker.
- **Domain:** framework-independent TypeScript and Vitest; embedded in API and
  operational worker, with no standalone hosting.
- **Database:** managed PostgreSQL/PostGIS, node-postgres, node-pg-migrate, and SQL
  constraints/access policies. Local database via Docker Compose.
- **Contracts:** checked-in JSON Schema Draft 7, Ajv for TypeScript, jsonschema for
  Python, generated TypeScript types, and shared conformance fixtures.
- **WhatsApp:** TypeScript interface, fake adapter, and conformance suite in this repo.
  The direct Meta Cloud API adapter comes from a separate contributor. Both are
  embedded in the API and operational worker.

## Shared build and release conventions

Use pnpm workspaces for TypeScript packages and an independent uv project/lockfile
inside `data-worker`. The repository root coordinates commands; Python is not an
npm runtime dependency. Plan root `dev`, `build`, `typecheck`, `lint`, and `test`
scripts plus Python-specific equivalents, but no such commands exist yet.

Add GitHub Actions checks for TypeScript type/lint checks, Python lint/tests,
cross-language contract fixtures, real-database integration tests, and a small
Playwright journey suite. Build deployable images/static assets after checks pass.
Never require real beneficiary data, live WhatsApp sends, or private satellite
credentials in ordinary CI. Build shared TypeScript packages before consumers;
package schema files into the Python image from the same repository revision.

Deploy migrations once, followed by compatible API/worker releases and the web
build. Support queued old event versions during rollout. Keep staging and production
databases, service credentials, messaging accounts, and object prefixes separate.
Version all images and record the application revision with processing results.

Decided: Google OAuth with email + password + TOTP as backup for sign-in; a mock
Monitor Ciudad feed as the first external source. Still open: object-storage provider,
basemap service, exact runtime/package pins, and hosting tiers and budget. See the
decisions table in [REQUIREMENTS.md](REQUIREMENTS.md#decisions).

## Dependency rules

- `contracts` has no dependencies on the other components.
- `domain` may use contracts, but never imports web or provider-specific code.
  Database access is through transaction/repository interfaces supplied by callers.
- `database` implements persistence interfaces and tenant-scoped transactions.
- `whatsapp` depends on contracts, never on case or household persistence.
- `api` and `operational-worker` compose the packages and enforce the required execution context.
- `data-worker` uses versioned JSON contracts and scoped internal API calls. It has
  no direct application database access and does not consume pg-boss jobs. See the
  [data-job protocol](contracts/data-jobs.md).
- `web` uses API contracts and never connects directly to the database or WhatsApp.
- Neither the API nor operational worker duplicates domain rules. Both use the same commands.
- Do not add separate analytics infrastructure, a vector database, or AI extraction
  to the initial implementation. Start with relational queries and structured intake.

## First runnable vertical slice

Deliver a local staff workflow with synthetic data:

1. Log in as a staff user of a seeded NGO.
2. Create a household using assisted intake, including an outage observation and
   sharing consent.
3. Open one case with a drinking-water need and a charging need.
4. Triage both needs and mark them shareable.
5. Log in as a vetted partner. See the needs in the partner's scope on the
   contactable list, and export it. Confirm the share events are logged.
6. Resolve one need with a disposition. Keep the case open until the other also has
   a disposition.

This slice establishes the case and sharing model before adding asynchronous messaging.
Use a development-only identity fixture if necessary; it must be disabled outside
local development and must not replace production authentication.

## Implementation milestones

### 1. Workspace and persistence

- Set up package management, TypeScript configuration, linting, and development commands.
- Provide local PostgreSQL/PostGIS configuration and an environment template.
- Pin compatible Node.js/pg-boss/PostgreSQL versions; add the worker Docker build,
  local Compose setup, and a proposed Render service configuration.
- Implement organization, membership, household/contact, assessment, observation,
  case, and need migrations with synthetic seed data.
- Establish authenticated organization context and test cross-organization denial.

Exit: a developer can start the application and database using documented commands,
sign in locally, and create/retrieve an assisted-intake case through the UI.

### 2. Triage and partner sharing

- Add staff queues, household case history, triage, and need dispositions.
- Add partner organizations, vetting, and scopes, plus partner sign-in.
- Add the contactable list view, watermarked exports, and share events.
- Add consent withdrawal and a sharing-history audit.

Exit:

- The vertical slice above works.
- Partners never see households without consent, outside their scope, or before
  vetting.
- Every export matches its logged share events.
- Withdrawing consent removes a household from all later lists.

### 3. WhatsApp intake

- Implement and exercise the fake adapter before using provider credentials.
- Add verified webhooks, durable inbox/outbox, idempotent workers, and conversation state.
- Implement the Spanish structured intake as "Metron Reporter": confirmation,
  separate sharing consent, corrections, opt-out, `ESTADO`, the urgent path, and
  handoff.
- Add share notices and resident follow-ups ("¿Recibiste ayuda?").
- Track outreach campaign attribution without treating an invitation as identity proof.
- Publish the adapter interface and conformance suite for the WhatsApp contributor.

Exit:

- Duplicate, delayed, and retried messages do not create duplicate needs or
  follow-ups.
- Interrupted conversations resume.
- A confirmed intake appears in the staff queue.
- The fake adapter passes the conformance suite.

### 4. Review and visibility

- Add comparable-observation rules and a human review queue.
- Implement the data-job API, leases, shared JSON schemas, and Python fixture pipeline.
- Add an independently built Python worker image and deployment configuration.
  Implement the mock Monitor Ciudad source first.
- Add aggregate area conditions, the need demand map, freshness, and metrics, with
  small-cell suppression.
- Keep partner-reported outcomes separate from resident-reported outcomes.

Exit: conflicting neighborhood reports never automatically deny aid; unknown areas
remain unknown; access restrictions apply to dashboards and exports as well as cases.
Expired or repeated data jobs cannot duplicate evidence, and Python results cannot
change assistance decisions directly.

### 5. Pilot readiness

- Replace local identity fixtures with production authentication and role management.
- Verify permissions, retention, backup restore, monitoring, failed-job handling,
  and staff fallback procedures.
- Confirm the following with CSL: partner vetting and data-handling statement, list
  fields, urgent referral content, staffed hours, and the WhatsApp integration
  agreement.

Exit: a bounded pilot can be operated by named staff with recovery and support paths.

### Later: in-app fulfillment

Only if CSL or a partner later runs deliveries in this platform, add the following
from PLATFORM_PLAN.md, with their original invariants:

- water supply, allocations, delivery runs, and deliveries
- charging sites, slots, bookings, and sessions

### Later: multiple organizations

Add scoped sharing agreements, case referrals, recipient acceptance, responsibility
handoffs, revocation, and audit trails. Preserve organization isolation from day one;
do not introduce global beneficiary matching as an incidental feature.

## High-value verification cases

- One organization cannot access another's case by guessing an ID.
- Two households sharing a phone stay distinct.
- Restoration does not close an unmet water need.
- A partner cannot see a household without sharing consent, outside its scope, or
  before vetting.
- Suspending a partner immediately ends its list access and expires its export links.
- A partner-reported "helped" does not resolve a need without a CSL disposition.
- Reports at different times can describe a transition instead of a contradiction.
- A correction retains provenance without creating a second active need unintentionally.

## Planning status

All components are planned, not implemented. Detailed entities and operational
assumptions are in [PLATFORM_PLAN.md](../PLATFORM_PLAN.md). Track implementation
progress against the exit criteria above rather than treating directory creation
as feature completion.
