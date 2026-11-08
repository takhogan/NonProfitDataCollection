# Aid coordination platform

A **data aggregation platform** for Venezuela. It collects reports of power and water
cuts and of household needs, and turns them into area-level indicators. Providers
(NGOs, water distributors, charging hosts) log in, see which areas need help and which
are uncovered, and act with their own resources. It is not an aid dispatch system.
Residents report through "Metron Reporter" on WhatsApp. The first operating NGO is
Ciudadanía Sin Límites in Caracas.

## Current state

This repository contains the product plan, the requirements, and a first runnable
Python API at [`components/whatsapp/api`](components/whatsapp/api/README.md). It covers:

- assisted intake
- household and case retrieval
- tenant isolation tests
- idempotency
- WhatsApp webhook persistence

The API uses SQLite locally. There is no worker, web app, or live integration yet.

- [Product plan and logical schema](PLATFORM_PLAN.md)
- [Component stacks, boundaries, and implementation roadmap](components/README.md)
- [Requirements: pilot context, roles, threat model, and per-component features](components/REQUIREMENTS.md)

The first release serves one NGO while enforcing organization ownership in the
data model. Later releases add explicit referrals and controlled collaboration
between organizations.

## Repository structure

```text
components/
  web/          Provider portal, operating-NGO console, and public dashboard
  api/          Authenticated application API and inbound webhooks (design)
  operational-worker/  Python intake conversation, messaging, and operational jobs
  data-worker/         Python external-data and geospatial processing
  domain/       Reports, needs, privacy profiles, indicators, providers, review
  database/     Schema, migrations, access policies, and synthetic seed data
  contracts/    Versioned request, response, event, and intake definitions
  whatsapp/     WhatsApp provider adapter and message normalization
    api/        Current Python backend implementation (FastAPI)
```

## Implementation baseline

The stack was decided on 7 November 2026, following the first implementation.

- **Backend:** one Python codebase for the API, operational worker, domain logic,
  persistence, and WhatsApp adapter.
  - Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic, and pytest.
  - The API and the operational worker are two processes started from the same
    package and image.
  - The directories under `components/` describe responsibilities. They are not
    separately deployed microservices.
- **Database:** PostgreSQL with PostGIS for CI integration tests, staging, and
  production. SQLite is allowed only for quick local demos. Tenant policies and
  spatial behavior must be tested on PostgreSQL.
- **Jobs:** the operational worker claims jobs from application-owned PostgreSQL tables
  with `SELECT … FOR UPDATE SKIP LOCKED`. No separate queue broker is used.
- **Data worker:** a separate Dockerized
  [Python data worker](components/data-worker/README.md) for external-source and
  geospatial processing. It claims data jobs through a versioned internal API, not the
  database. See the [data-job contract](components/contracts/data-jobs.md).
- **Web:** React, TypeScript, and Vite. TypeScript API types are generated from the
  backend's OpenAPI document.

Proposed hosting: Render web service (API), Render background worker (same image,
worker command), and managed Render Postgres/PostGIS, colocated in Virginia, subject to
NGO hosting requirements. No hosting resources have been provisioned.

Start with synthetic data and assisted intake. Add real WhatsApp traffic after
the assisted-reporting, aggregation, and provider workflow works. The architecture supports a fake
messaging adapter for local iteration without provider credentials.

## Product rules

- Track outage observations, household needs, and assistance separately.
- A shared phone is not a unique person or household identifier.
- Conflicting reports create review work; they do not automatically deny aid.
- Missing area reports mean unknown conditions.
- The platform aggregates and informs; providers act. Nothing here dispatches aid or
  decides who receives it.
- Each operating NGO picks a privacy profile. `protective` stores no names, addresses,
  or GPS, and uses meeting points instead.
- Aggregates are area-level and small-cell-suppressed. Unknown areas are never shown as
  zero.
- Repeat reports from one reporter count once. Disagreement never removes a report.
- Provider contact lists include only reporters who opted in, are vetted-only, and are
  always logged.
- Never sum different units (liters, people, devices, reporters, households).
- Every operational record belongs to an organization; access is enforced server-side.
- Use synthetic people and contact details in development. Do not commit personal
  information, credentials, database exports, or raw message payloads.
