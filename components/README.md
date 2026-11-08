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

Proposed production topology: a Render web service running the FastAPI app, a Render
Background Worker running the operational worker from the same Python image, and
managed Render Postgres/PostGIS, all in the same region. Start with one operational
worker instance. Add the separate Python data worker when external-source processing is
implemented. See the
[operational worker deployment plan](operational-worker/README.md)
for local development, queue consistency, release steps, and operational checks.

## Requirements

Feature requirements, priorities (P0 pilot / P1 during pilot / P2 later), and
acceptance criteria live in [REQUIREMENTS.md](REQUIREMENTS.md) and each component's
`REQUIREMENTS.md`. This file covers architecture and stack.

## Component responsibilities

1. **[web](web/README.md):** The provider portal (areas of need, map, coverage,
   activity log, alerts, exports, API keys, contact list); the operating-NGO console
   (intake, data health, review, meeting points, broadcasts, admin); and the optional
   public dashboard.
2. **[api](api/README.md):** Authentication, organization authorization, input
   validation, application endpoints, provider webhook handling, and read models.
3. **[operational-worker](operational-worker/README.md):** Python reporting
   conversation, outbound messages (refresh prompts, broadcasts), indicator and
   coverage refresh, provider alerts, evidence ingestion, and retention.
4. **[data-worker](data-worker/README.md):** Python source ingestion, geospatial
   processing, quality checks, and provenance-rich evidence candidates.
5. **[domain](domain/README.md):** Reports and needs, privacy-profile enforcement,
   area indicators and ranking, coverage, provider rules, reporter permissions, and
   data-quality review.
6. **[database](database/README.md):** Relational schema, tenant isolation,
   constraints, transaction primitives, migrations, indexes, and synthetic seeds.
7. **[contracts](contracts/README.md):** Runtime-validated API payloads, event
   schemas, intake versions, enumerations, errors, and quantity/time conventions.
8. **[whatsapp](whatsapp/README.md):** Provider-neutral adapter interface, fake
   adapter, and conformance suite. A separate contributor builds the production Meta
   Cloud API adapter against that interface.

## Tech stack by component

The stack was decided on 7 November 2026: a **Python backend**, following the first
implementation at [`whatsapp/api`](whatsapp/api/README.md). The web app stays
React/TypeScript. Pin compatible versions and commit lockfiles.

- **Backend (API + operational worker + domain + persistence + WhatsApp adapter):**
  one Python 3.11+ package.
  - FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, psycopg 3, HTTPX, and
    standard-library JSON logging.
  - pytest + HTTPX for tests, and Ruff for lint and format.
  - Built into one Docker image with two start commands (`uvicorn` API, worker loop).
  - Packaged with `pyproject.toml` and a committed lockfile (uv recommended, matching
    the data worker).
- **Web:** React, TypeScript, Vite, React Router, TanStack Query, React Hook Form,
  CSS Modules; MapLibre when maps are introduced.
  - API types are generated from the backend's OpenAPI with `openapi-typescript`.
  - Deployed as a static build on Render.
- **Data worker:** Python, uv, HTTPX, jsonschema, pytest, and Ruff; add NumPy/pandas,
  GeoPandas, Rasterio, or Xarray per pipeline. Deployed as a separate Docker worker
  with its own lockfile.
- **Database:** managed PostgreSQL/PostGIS. SQLAlchemy models, Alembic migrations, and
  raw SQL in migrations for row-level security, constraints, exclusion constraints, and
  spatial indexes. Local PostgreSQL via Docker Compose. SQLite is for quick demos only.
- **Jobs:** application-owned PostgreSQL job tables claimed with
  `FOR UPDATE SKIP LOCKED`. No external broker and no Node-only queue.
- **Contracts:** Pydantic models are the source of truth.
  - FastAPI's OpenAPI document and exported JSON Schemas (events, data jobs) are
    checked in, with a CI drift check.
  - Shared fixtures run through Pydantic and the data worker's `jsonschema`.
- **WhatsApp:** a Python adapter interface, fake adapter, and conformance suite. The
  Meta Cloud API adapter is built by the separate contributor in the same backend
  package.

## Shared build and release conventions

The repository has three projects, each with its own lockfile:

- the Python backend
- the Python data worker
- the web app (npm or pnpm)

Plan root `dev`, `lint`, `test`, and `build` commands that call each project. No such
commands exist yet; the backend currently runs from
[`whatsapp/api`](whatsapp/api/README.md).

Add GitHub Actions checks for:

- backend Ruff, type checks (mypy or pyright), and pytest against real PostgreSQL
- data worker lint and tests
- OpenAPI and JSON Schema drift
- shared contract fixtures
- web type, lint, and test checks
- a small Playwright journey suite

Build deployable images and static assets after the checks pass. Never require real
beneficiary data, live WhatsApp sends, or private satellite credentials in ordinary CI.
Package the exported schema files into the data worker image from the same repository
revision.

Deploy migrations once, followed by compatible API/worker releases and the web
build. Support queued old event versions during rollout. Keep staging and production
databases, service credentials, messaging accounts, and object prefixes separate.
Version all images and record the application revision with processing results.

Decided:

- Python backend.
- Google OAuth with email + password + TOTP as backup for sign-in. The current JWT
  bearer login is an interim implementation.
- A mock Monitor Ciudad feed as the first external source.

Still open: object-storage provider, basemap service, exact runtime/package pins,
hosting tiers and budget, and the backend's final location in the repo (it lives under
`whatsapp/api` today). See the
decisions table in [REQUIREMENTS.md](REQUIREMENTS.md#decisions).

## Dependency rules

These rules apply between modules of the one Python backend package. The current
mapping in `whatsapp/api/app` is noted in brackets.

- Contracts (`app/contracts`) have no dependencies on other modules.
- Domain (`app/domain`) may use contracts and the SQLAlchemy session it is given.
  - It never imports FastAPI, request objects, or provider-specific code.
  - Every function takes an explicit request context (`ctx`).
- Persistence (`app/models`, `app/db.py`, migrations) implements tenant-scoped
  sessions and transactions.
- The WhatsApp adapter depends on contracts, never on case or household persistence.
- API routers (`app/routers`) and the operational worker compose these modules and
  enforce the required execution context.
- The data worker uses versioned JSON contracts and scoped internal API calls. It has
  no direct application database access and does not read the job tables. See the
  [data-job protocol](contracts/data-jobs.md).
- `web` uses API contracts and never connects directly to the database or WhatsApp.
- Neither the API nor operational worker duplicates domain rules. Both use the same commands.
- Do not add separate analytics infrastructure, a vector database, or AI extraction
  to the initial implementation. Start with relational queries and structured intake.

## First runnable vertical slice

Deliver a local workflow with synthetic data:

1. Log in as a coordinator of a seeded NGO (protective profile).
2. Enter three assisted reports in one sector and one in another. Use meeting points,
   include drinking-water and charging needs, and opt one reporter into the contact
   list.
3. See the area indicators update, with the small sector suppressed and an untouched
   sector shown as unknown.
4. Log in as a provider. See the areas of need and the coverage view, log a water
   distribution activity in the first sector, and watch coverage change.
5. As a vetted provider, see the one opted-in reporter (alias, sector, meeting point,
   phone) and export the list. Confirm the share events are logged.
6. Confirm that no name, address, or GPS was stored anywhere.

This slice establishes the aggregation and provider model before adding asynchronous
messaging. A development-only identity fixture is acceptable locally, but must not
replace production authentication.

## Implementation milestones

### 1. Workspace and persistence

- Status: partly done. The Python API in `whatsapp/api` has models, an Alembic
  migration, seeds, JWT login, assisted intake, tenant isolation, and idempotency.
- Point local development and CI at PostgreSQL/PostGIS via Docker Compose. Keep SQLite
  only for quick demos.
- Pin Python and PostgreSQL versions. Add the backend Docker image (API and worker
  commands), Compose setup, and a proposed Render configuration.
- Migrate to the report-centric model: reports, needs (new categories), privacy profile
  versions, meeting points, and reporter keys. Retire case records from the core.

Exit: a developer can start the stack, sign in locally, and submit and retrieve an
assisted report through the UI.

### 2. Aggregation and provider portal

- Indicator cells, suppression, coverage and confidence labels, and the areas-of-need
  ranking.
- Provider organizations, vetting, and scope; activity logging and coverage.
- Aggregate exports, API keys, and the opt-in contact list with share events.

Exit:
- The vertical slice above works.
- Repeat reporters count once.
- Unknown areas are never zero.
- Suppression holds in every view, export, and API response.
- Unvetted providers see no contact data.

### 3. WhatsApp reporting

- The fake adapter first. Then verified webhooks, durable inbox/outbox, idempotent
  workers, and conversation state.
- The Spanish "Metron Reporter" flow, with profile-dependent location (meeting points),
  three separate permissions, corrections, `ACTUALIZAR`/`DÓNDE`/`PERMISOS`/`BAJA`, and
  the urgent path.
- Publish the adapter interface and conformance suite for the WhatsApp contributor.

Exit:
- Duplicate, delayed, and retried messages create no duplicate reports.
- Conversations resume.
- Confirmed reports reach indicators within 5 minutes.

### 4. Freshness, alerts, quality, and external context

- Refresh prompts, need stale/expiry, area broadcasts, and provider alerts.
- Comparison rules, the review queue, and outlier and flood detection.
- The data-job API and the Python worker with the mock Monitor Ciudad source.
- The optional public dashboard, with delay and a kill switch.

Exit:
- Disagreement never removes a report.
- Expired needs leave indicators.
- Alerts contain no personal data.
- Data-worker results cannot change report or need state.
- The public dashboard is coarser and delayed.

### 5. Pilot readiness

- Production authentication; permissions; retention and profile purges; backup
  restore; monitoring; fallback procedures.
- Confirm with CSL: provider vetting and statement, meeting points, urgent referral
  content, the public dashboard decision, and the WhatsApp integration agreement.

Exit: a bounded pilot can be operated by named staff, with recovery and support paths.

### Later

- **Case management module** (`DOM-090`): optional per-NGO household cases and queues,
  and possibly in-app fulfillment.
- **Multiple organizations** (`DOM-095`): cross-tenant aggregates under sharing
  agreements. No global beneficiary matching.

## High-value verification cases

- One organization cannot read another's reports, indicators, or API data by guessing
  an ID.
- A protective-profile tenant never stores or returns names, addresses, or GPS.
- The same reporter reporting three times counts once in a cell.
- An area with no reports shows as unknown, never as zero or "OK".
- A cell below *k* is suppressed in the UI, exports, the API, alerts, and the public
  dashboard.
- Restoration does not resolve an unmet water need.
- Logging a provider activity marks the area covered without changing any need.
- Reports at different times describe a transition, not a contradiction.
- Disagreement with neighbors or external data never removes a report from aggregates.

## Planning status

Most components are planned, not implemented; a first Python API exists in `whatsapp/api`. Detailed entities and operational
assumptions are in [PLATFORM_PLAN.md](../PLATFORM_PLAN.md). Track implementation
progress against the exit criteria above rather than treating directory creation
as feature completion.
