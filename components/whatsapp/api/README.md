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

**Deployment:** see [DEPLOY.md](DEPLOY.md) for Cloud Run (API + worker) with
Cloud SQL and Secret Manager. In production (`APP_ENV=production`) startup fails
fast if any secret is missing or insecure, and SQLite is rejected.

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

Password for all: the value of `SEED_DEMO_PASSWORD` (defaults to
`local-demo-pass` locally if unset).

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
  -d '{"email":"ana@aguazul.org","password":"local-demo-pass"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

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

### Deployed webhook (Google Cloud)

The webhook runs in its own GCP project, deployed by
[`deploy/gcloud-deploy.sh`](deploy/gcloud-deploy.sh). The script runs in re-runnable
steps (`project apis registry build sql sa secrets migrate service url`).
[`deploy/verify.sh`](deploy/verify.sh) runs the synthetic smoke tests.
[DEPLOY.md](DEPLOY.md) is the general walkthrough. This deployment differs from it
in a few ways: region `us-east4`, a dedicated runtime service account, and no
worker service yet.

| Resource | Value |
|----------|-------|
| Project | `csl-metron-webhook` (billing: Firebase Payment account) |
| Region | `us-east4` (Virginia, outside Venezuela) |
| Service | Cloud Run `whatsapp-webhook`, public, min 0 / max 3 instances |
| Webhook URL | `https://whatsapp-webhook-3cgqtlfqwq-uk.a.run.app/webhooks/whatsapp` |
| Database | Cloud SQL `aid-pg`, Postgres 16, db-f1-micro, 10 GB SSD, daily backups. No authorized networks: the only access path is the Cloud SQL connector. |
| Migrations | Cloud Run Job `aid-migrate` (`python -m scripts.migrate`), run once per deploy and never on container start |
| Secrets | Secret Manager (regional, us-east4): `database-url`, `jwt-secret`, `verify-token`, `whatsapp-app-secret`, `whatsapp-token`, `whatsapp-phone-id`, `seed-demo-password` |
| Runtime SA | `webhook-run@csl-metron-webhook.iam.gserviceaccount.com`, with `roles/cloudsql.client` plus `secretAccessor` on each of those secrets only |

The URL is public because Meta must reach it. Each `POST` is authenticated by its
`X-Hub-Signature-256` HMAC: a missing or invalid signature returns **401** and
nothing is stored. Production startup fails if any secret is missing.

Redeploy after code changes (from this directory):

```bash
./deploy/gcloud-deploy.sh build && ./deploy/gcloud-deploy.sh migrate && ./deploy/gcloud-deploy.sh service
./deploy/verify.sh
```

**Handing over to Meta.** The WhatsApp contributor owns these steps, not this script:

1. Replace the placeholder secrets with real values. Each is read from stdin, so it
   never appears on the command line:
   ```bash
   gcloud secrets versions add whatsapp-app-secret --project=csl-metron-webhook --data-file=-   # Meta App Secret
   gcloud secrets versions add whatsapp-token      --project=csl-metron-webhook --data-file=-   # permanent token
   gcloud secrets versions add whatsapp-phone-id   --project=csl-metron-webhook --data-file=-   # phone number id
   ```
   Then run `./deploy/gcloud-deploy.sh service` so a new revision picks them up.
   Until the real `APP_SECRET` is in place, every genuine Meta `POST` gets 401.
2. In Meta → WhatsApp → Configuration → Webhook, set the callback URL to the
   webhook URL above. Set the verify token to the output of
   `gcloud secrets versions access latest --secret=verify-token --project=csl-metron-webhook`.
   Then subscribe to the `messages` field.

Logging: uvicorn access logs are off, because they would include
`hub.verify_token`. Cloud Run's own request log still records the full handshake
URL, so rotate `verify-token` if that log is ever exposed.

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
