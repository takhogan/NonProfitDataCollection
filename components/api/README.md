# Application API

Own the authenticated HTTP boundary and compose domain commands with persistence.

## Endpoint groups

- Current user, authorized organization memberships, and staff assignments.
- Households, contacts, assessments, observations, cases, and needs.
- Triage, shareable flags, partner organizations, vetting, and scopes.
- Partner contactable list, watermarked exports, share events, and partner outcomes.
- Deferred: water/charging fulfillment endpoints (see REQUIREMENTS.md `API-110`).
- Reviews, dashboard read models, permissions, and later referrals.
- WhatsApp inbound message and delivery-status webhooks.
- Authenticated internal data-job claim, heartbeat, completion, failure, and scoped
  artifact access for the Python worker; see [the job contract](../contracts/data-jobs.md).

Validate request bodies with shared runtime contracts. Derive organization access
from authenticated membership, not a trusted request field. Pass explicit tenant and
actor context into transactions, and authorize both reads and mutations.

Accept idempotency keys for exports, outcomes, and other retryable mutations. Return
structured validation, permission, conflict, and capacity errors. Authenticate
provider webhooks using the adapter; persist accepted events before acknowledging.
Do not perform long-running intake or network sends inside the webhook request.

First deliverable: authorized assisted-intake creation and household/case retrieval.

## Proposed tech stack and deployment

- TypeScript + Node.js LTS + Fastify, with JSON Schema request/response definitions.
- Fastify's Ajv validation and explicit response schemas; Pino structured logging.
- `node-postgres` through the database package for transactional persistence.
- An OpenID Connect integration for staff sign-in; provider selection is an open
  operational decision. Use a maintained OIDC client, not handwritten token verification.
- Vitest and Fastify request injection, with real PostgreSQL for integration tests.
- Dockerized Render Web Service; one instance initially, colocated with the database.

Staff authentication and worker authentication are separate. Plan an OIDC authorization
code flow with server-side session storage and secure HttpOnly cookies. Protect
mutations against CSRF, validate redirect destinations, and restrict credentialed
CORS to the configured staff-app origin. For the pilot Python worker, use a rotatable
service credential mapped to allowed organizations/job types; never reuse a staff cookie.

## Internal modules

`src/plugins` owns configuration, logging, authentication, database context, and
error mapping. `src/routes` groups staff API, webhook, and internal-worker routes.
`src/application` composes domain commands with transactions; `src/read-models`
contains scoped dashboard and search queries. No business logic belongs in route handlers.

Proposed routes include `POST /v1/assessments`, `GET /v1/cases/:id`,
`GET /v1/partner/list`, `POST /v1/partner/exports`, and
`POST /v1/partner/needs/:ref/outcome`. See [REQUIREMENTS.md](REQUIREMENTS.md).
Internal routes follow the separate data-job protocol. Add cursor pagination,
bounded date/area filters, request IDs, and a consistent error envelope.

For idempotent mutations, scope the key to actor/organization and operation, store
a request digest and result, and reject reuse with different input. For editable
records, use a version field to detect stale writes. A database conflict becomes a
clear client error rather than silent last-write-wins behavior.

## Release and verification

Expose liveness and readiness separately; readiness includes database availability.
Apply controlled migrations before rollout, then deploy compatible API and workers.
Test authentication, role checks, cross-tenant IDs, malformed input, concurrent
exports, partner scope, duplicate commands, and internal credential scope before live collection.

Reference: [Fastify validation and serialization](https://fastify.dev/docs/latest/Reference/Validation-and-Serialization/).
