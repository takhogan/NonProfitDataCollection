# Aid coordination platform

A platform for NGOs in Venezuela to collect reports of power and water cuts,
understand household needs, and share them with partner organizations that deliver
water and charging access. Residents see the service as "Metron Reporter"; the pilot
NGO is Ciudadanía Sin Límites in Caracas.

## Current state

This repository contains the product plan and component architecture. It does not
yet contain a runnable application, database migrations, or live integrations.

- [Product plan and logical schema](PLATFORM_PLAN.md)
- [Component stacks, boundaries, and implementation roadmap](components/README.md)
- [Requirements: pilot context, roles, threat model, and per-component features](components/REQUIREMENTS.md)

The first release serves one NGO while enforcing organization ownership in the
data model. Later releases add explicit referrals and controlled collaboration
between organizations.

## Repository structure

```text
components/
  web/          Staff dashboard, household CRM, review, and partner portal
  api/          Authenticated application API and inbound webhooks
  operational-worker/  TypeScript intake, notifications, and operational jobs
  data-worker/         Python external-data and geospatial processing
  domain/       Needs, cases, consent, partner sharing, and review rules
  database/     Schema, migrations, access policies, and synthetic seed data
  contracts/    Versioned request, response, event, and intake definitions
  whatsapp/     WhatsApp provider adapter and message normalization
```

## Proposed implementation baseline

Use a TypeScript workspace with a React web application, Node.js API and operational worker,
and PostgreSQL with PostGIS. The proposed frameworks are React/Vite for the web
app and Fastify for the API, with pnpm managing the TypeScript workspace. The Python
data worker uses uv, HTTPX, and source-specific processing libraries. Exact supported
versions will be pinned when implementation begins. Keep the API and operational worker in one modular
application codebase with shared domain behavior; these directories are not a
commitment to independently deployed microservices.

Proposed operational worker deployment: a Dockerized TypeScript/Node.js process on Render
Background Workers, using pg-boss and managed PostgreSQL for durable jobs. Colocate
API, worker, and database; Virginia is the proposed pilot region, subject to NGO
hosting requirements. See the [worker stack and operating plan](components/operational-worker/README.md).
A separate Dockerized [Python data worker](components/data-worker/README.md) handles
external-source and geospatial processing. It claims jobs through a versioned internal
API, rather than consuming pg-boss jobs. See the [cross-language contract](components/contracts/data-jobs.md).
No hosting resources have been provisioned.

Start with synthetic data and assisted intake. Add real WhatsApp traffic after
the basic case, triage, and partner-sharing workflow works. The architecture supports a fake
messaging adapter for local iteration without provider credentials.

## Product rules

- Track outage observations, household needs, and assistance separately.
- A shared phone is not a unique person or household identifier.
- Conflicting reports create review work; they do not automatically deny aid.
- Missing area reports mean unknown conditions.
- The operating NGO collects, triages, and shares; partners fulfill. Partner exports
  include only consenting, in-scope households and are always logged.
- Water needs (drinking and other use, kept separate) use liters or people; charging
  needs use devices. Never sum different units.
- A partner-reported outcome is not proof of help; residents are asked directly.
- Every operational record belongs to an organization; access is enforced server-side.
- Use synthetic people and contact details in development. Do not commit personal
  information, credentials, database exports, or raw message payloads.
