# Application API

Own the authenticated HTTP boundary and compose domain commands with persistence.

## Endpoint groups

- Current user, authorized organization memberships, and staff assignments.
- Households, contacts, assessments, observations, cases, and needs.
- Water supplies, allocations, delivery runs/stops, and delivery recording.
- Charging sites, slots, reservations, and session recording.
- Reviews, dashboard read models, permissions, and later referrals.
- WhatsApp inbound message and delivery-status webhooks.

Validate request bodies with shared runtime contracts. Derive organization access
from authenticated membership, not a trusted request field. Pass explicit tenant and
actor context into transactions, and authorize both reads and mutations.

Accept idempotency keys for fulfillment and other retryable mutations. Return
structured validation, permission, conflict, and capacity errors. Authenticate
provider webhooks using the adapter; persist accepted events before acknowledging.
Do not perform long-running intake or network sends inside the webhook request.

First deliverable: authorized assisted-intake creation and household/case retrieval.

---

## Implementation (hackathon)

Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 + Alembic. SQLite locally
(swap `DATABASE_URL` for PostgreSQL in production). OpenAPI is exposed so the
frontend can generate TypeScript types.

### Quick start

```bash
cd components/whatsapp/api
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

cp .env.example .env          # edit secrets; never commit .env

.venv/bin/alembic upgrade head        # create tables
.venv/bin/python -m scripts.seed      # 2 orgs, 3 users, sample households

.venv/bin/uvicorn app.main:app --reload
```

- API docs / OpenAPI UI: http://127.0.0.1:8000/docs
- OpenAPI JSON (for TS codegen): http://127.0.0.1:8000/openapi.json
- Health: http://127.0.0.1:8000/health

Generate frontend types from a running server, e.g.:

```bash
npx openapi-typescript http://127.0.0.1:8000/openapi.json -o web/src/api-types.ts
```

### Demo logins

Password for all: `demo-pass`

| Email | Organization | Role |
|-------|--------------|------|
| ana@aguazul.org | Agua Azul | coordinator |
| luis@aguazul.org | Agua Azul | caseworker |
| maria@luzviva.org | Luz Viva | coordinator |

### Try the first deliverable

```bash
# 1. Log in -> JWT
TOKEN=$(curl -s localhost:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"ana@aguazul.org","password":"demo-pass"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 2. Who am I / my orgs
curl -s localhost:8000/me -H "authorization: Bearer $TOKEN"

# 3. Find my org id, then create an assisted intake (org id comes from the URL,
#    NEVER the body). Use the id printed by the seed script.
ORG=<agua-azul-org-id>
curl -s -X POST "localhost:8000/orgs/$ORG/households" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{"reference_code":"DEMO-1","estimated_member_count":4,
       "contacts":[{"preferred_name":"Carmen","preferred_language":"es"}],
       "observations":[{"service_type":"piped_water","status":"unavailable"}],
       "needs":[{"category":"water_delivery","requested_quantity":40,"unit":"liters","urgency":"urgent"}]}'

# 4. List org cases
curl -s "localhost:8000/orgs/$ORG/cases" -H "authorization: Bearer $TOKEN"
```

### Tests

```bash
.venv/bin/python -m pytest
```

Covered: auth, assisted intake (household + contacts + assessment + case + needs
in one transaction), household/case retrieval, **cross-organization isolation**
(org A cannot read or write org B's data), Idempotency-Key replay, and the
WhatsApp webhook (verification handshake, signature check, event persistence,
provider-message dedupe).

## Architecture notes

- **One APIRouter per endpoint group.** Implemented: `auth`, `me`, `households`,
  `cases`, `webhooks`. Stubbed empty for later: `water`, `charging`, `reviews`.
- **Tenant isolation.** Org-scoped routes live under `/orgs/{org_id}/...`.
  `get_org_context` (`app/deps.py`) verifies the caller has an active membership
  in that org and builds a `RequestContext(org_id, actor_id, membership_id, role)`.
  The org is taken from the URL + membership, **never** from the request body.
  A non-member or cross-org row returns **404** (not 403) so existence is not
  leaked.
- **Domain layer** (`app/domain/`) functions take `(ctx, db, ...)`, scope every
  query to `ctx.org_id`, and contain no HTTP concerns. Intake runs in one
  transaction.
- **Structured errors** (`app/errors.py`): `ValidationError`, `PermissionDenied`,
  `NotFound`, `Conflict`, `CapacityExceeded` → one JSON shape
  `{"error": {"code", "message", "details"}}`.
- **Idempotency** (`app/idempotency.py`): `Idempotency-Key` header stores the
  first result per `(org, endpoint, key)` in `idempotency_key`; retries replay it.
- **Webhooks** (`app/routers/webhooks.py`): `GET /webhooks/whatsapp` does the Meta
  handshake; `POST` verifies `X-Hub-Signature-256`, persists the raw payload to
  `inbound_event`, and returns 200 immediately. No LLM calls or outbound sends in
  the request. A separate worker (not in this deliverable) polls unprocessed
  `inbound_event` rows — see `components/worker`.

## Environment variables

See `.env.example`. `DATABASE_URL`, `JWT_SECRET`, and the WhatsApp secrets
(`WHATSAPP_TOKEN`, `APP_SECRET`, `VERIFY_TOKEN`, `PHONE_NUMBER_ID`) come from the
environment / `.env`. Never commit `.env`.

## Layout

```
app/
  main.py          FastAPI app, router mounting, error handlers
  config.py        Settings from env/.env
  db.py            Engine, session, get_db dependency
  security.py      JWT + password hashing
  deps.py          get_current_user, get_org_context
  context.py       RequestContext(org_id, actor_id, ...)
  errors.py        Structured errors + handlers
  idempotency.py   Idempotency-Key storage/replay
  models/          SQLAlchemy ORM (maps to components/database)
  contracts/       Pydantic request/response schemas (maps to components/contracts)
  domain/          Business logic, (ctx, db, ...) (maps to components/domain)
  routers/         One APIRouter per endpoint group
migrations/        Alembic
scripts/seed.py    Synthetic demo data
tests/             pytest + httpx
```
