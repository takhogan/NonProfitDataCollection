# Application API

Own the authenticated HTTP boundary and compose domain commands with persistence.

## Endpoint groups

- Current user, memberships, and privacy-profile summary.
- Reports (assisted intake, browsing), meeting points, and campaigns.
- Area indicators, areas of need, coverage, area detail, and trends.
- Providers: organizations, vetting, activities, alerts, API keys, the opt-in contact
  list, and exports.
- The public dashboard API (`/public/v1`), with a kill switch.
- Review, privacy profile and policies, broadcasts, and audit.
- Deferred: case management (`DOM-090`).
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

## Current implementation

The working API lives at [`components/whatsapp/api`](../whatsapp/api/README.md). It
covers:

- assisted intake
- household and case retrieval
- cross-organization isolation tests
- `Idempotency-Key` replay
- the WhatsApp verification handshake and signed inbound-event persistence

This file and [REQUIREMENTS.md](REQUIREMENTS.md) describe the intended behavior. The
implementation README describes how to run what exists today.

### Gaps between the implementation and requirements

| Area | Today | Required |
|---|---|---|
| Staff auth | Email + password, JWT bearer token | Google OIDC, with email + password + TOTP backup; server-side sessions in `HttpOnly` cookies; CSRF protection (`API-010`, `API-013`) |
| Database | SQLite locally, tenant scoping in code | PostgreSQL/PostGIS with row-level security as a second layer (`DB-002`) |
| Routes | `/orgs/{org_id}/...`, unversioned | `/v1/...` with the org derived from the session membership (`API-001`, `API-011`). Keep the 404-on-other-org behavior, which is already correct. |
| Error envelope | `{"error": {code, message, details}}` | `{code, message_key, details, request_id}` (`CON-040`) |
| Idempotency | Stored per (org, endpoint, key) | Also store a request digest, and reject reuse with different input (`DOM-002`) |
| Data model | Households + cases + needs (`water_delivery` with liters) | Report-centric: reports, needs (`water_drinking`, `water_other`, `charging`), privacy profile, meeting points, reporter keys (`DOM-010`–`034`). Cases are deferred (`DOM-090`). |
| Water/charging routers | Empty stubs | Remove; fulfillment is out of scope |
| Indicators, providers, public API, review | Not started | `API-040`–`045`, `API-050`–`064`, `API-070`–`071`, `API-080`–`081` |

## Tech stack and deployment

The stack was decided on 7 November 2026: Python, following the first implementation.

- Python 3.11+, FastAPI, and Pydantic v2 request/response models. The generated
  OpenAPI document is checked in for web type generation.
- SQLAlchemy 2.0 sessions (psycopg 3 on PostgreSQL) and Alembic migrations. The domain
  layer receives an explicit request context and session.
- Standard-library JSON logging with request IDs, redacted per `API-102`.
- Google sign-in through a maintained OIDC client (Authlib). Password hashing with
  Argon2id (`argon2-cffi`), and TOTP with `pyotp`. Never write token verification by
  hand.
- pytest with HTTPX `TestClient`. Integration tests run on real PostgreSQL in CI.
- Docker image served by `uvicorn` (or gunicorn with uvicorn workers) on a Render web
  service. One instance initially, colocated with the database. The worker runs from
  the same image.

Staff authentication and worker authentication are separate. Use an OIDC
authorization code flow with server-side session storage and secure `HttpOnly`
cookies. Protect mutations against CSRF, validate redirect destinations, and restrict
credentialed CORS to the configured web origin. Bearer tokens kept in browser storage
are not acceptable for staff (SEC-07). For the Python data worker, use a rotatable
service credential mapped to allowed organizations and job types; never reuse a staff
session.

## Internal modules

These modules are inside the backend package (currently `whatsapp/api/app`):

- `config.py`, `db.py`, `deps.py`, `security.py`, and `errors.py`: configuration,
  sessions, auth and organization context, and error mapping.
- `routers/`: one `APIRouter` per endpoint group, plus webhook and internal data-job
  routers.
- `domain/`: commands that take `(ctx, session, ...)`.
- `read_models/` (planned): scoped dashboard, demand, and search queries.

No business logic belongs in route handlers.

Proposed routes include `POST /v1/reports`, `GET /v1/indicators`,
`GET /v1/areas-of-need`, `GET /v1/coverage`, `POST /v1/activities`,
`GET /v1/contact-list`, and `GET /public/v1/indicators`. See [REQUIREMENTS.md](REQUIREMENTS.md).
Internal routes follow the separate data-job protocol. Add cursor pagination, bounded
date and area filters, request IDs, and a consistent error envelope.

For idempotent mutations, scope the key to the actor, organization, and operation.
Store a request digest and result, and reject reuse with different input. For editable
records, use a version field to detect stale writes. A database conflict becomes a
clear client error rather than silent last-write-wins behavior.

## Release and verification

Expose liveness and readiness separately; readiness includes database availability.
Apply controlled migrations before rollout, then deploy compatible API and workers.
Test authentication, role checks, cross-tenant IDs, malformed input, concurrent
exports, provider scope, profile enforcement, suppression, duplicate commands, and internal credential scope before live collection.

Reference: [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/).
