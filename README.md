# Aid coordination platform

A platform for NGOs in Venezuela to collect reports of power and water cuts,
understand household needs, and coordinate water deliveries and charging access.

## Current state

This repository contains the product plan and component architecture. It does not
yet contain a runnable application, database migrations, or live integrations.

- [Product plan and logical schema](PLATFORM_PLAN.md)
- [Component boundaries and implementation roadmap](components/README.md)

The first release serves one NGO while enforcing organization ownership in the
data model. Later releases add explicit referrals and controlled collaboration
between organizations.

## Repository structure

```text
components/
  web/          Staff dashboard, household CRM, and fulfillment screens
  api/          Authenticated application API and inbound webhooks
  worker/       Reliable background processing and outbound messages
  domain/       Needs, cases, allocations, fulfillment, and review rules
  database/     Schema, migrations, access policies, and synthetic seed data
  contracts/    Versioned request, response, event, and intake definitions
  whatsapp/     WhatsApp provider adapter and message normalization
```

## Proposed implementation baseline

Use a TypeScript workspace with a React web application, Node.js API and worker,
and PostgreSQL with PostGIS. The exact frameworks and supported versions will be
selected when implementation begins. Keep the API and worker in one modular
application codebase with shared domain behavior; these directories are not a
commitment to independently deployed microservices.

Start with synthetic data and assisted intake. Add real WhatsApp traffic after
the basic case and fulfillment workflow works. The architecture supports a fake
messaging adapter for local iteration without provider credentials.

## Product rules

- Track outage observations, household needs, and assistance separately.
- A shared phone is not a unique person or household identifier.
- Conflicting reports create review work; they do not automatically deny aid.
- Missing area reports mean unknown conditions.
- Water is fulfilled in liters; charging is fulfilled in device sessions.
- Allocation and booking are not proof of successful fulfillment.
- Every operational record belongs to an organization; access is enforced server-side.
- Use synthetic people and contact details in development. Do not commit personal
  information, credentials, database exports, or raw message payloads.
