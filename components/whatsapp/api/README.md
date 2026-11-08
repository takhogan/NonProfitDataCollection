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

### Staff sign-in and routes

Staff API routes live under `/v1` and use **server-side sessions in an
`HttpOnly`/`Secure`/`SameSite=Lax` cookie** (`__Host-sid`), with a 30-minute
idle timeout and a 12-hour absolute limit. The organization comes from the
session's active membership, never from the URL or body.

| Route | Purpose |
|-------|---------|
| `POST /v1/auth/password/login` | Email + password (Argon2id). Sets a 5-minute pre-auth session; returns `{stage, csrf_token}` |
| `POST /v1/auth/totp/enroll` | First sign-in only: returns the TOTP secret and `otpauth://` URI |
| `POST /v1/auth/totp/verify` | TOTP code → rotated, active session |
| `GET /v1/auth/oidc/google/start?next=/path` | Google sign-in (authorization code + PKCE); invited, verified emails only |
| `GET /v1/auth/oidc/google/callback` | Redirects back to `WEB_ORIGIN` + `next` |
| `POST /v1/auth/logout` | End this session |
| `GET /v1/me` | Memberships, active org and role, session info, CSRF token |
| `POST /v1/me/active-organization` | Switch org among the caller's own memberships |
| `POST /v1/me/revoke-all` | End all of the caller's sessions |
| `GET /v1/admin/users/{id}/sessions`, `POST .../revoke-sessions` | Org admin: list or end a member's sessions |
| `POST /v1/households`, `GET /v1/households/{id}`, `GET /v1/cases` | Assisted intake and retrieval |
| `GET /livez`, `GET /readyz` (`/health` = `/livez`) | Liveness; readiness checks the database |

Every cookie-authenticated `POST`/`PUT`/`PATCH`/`DELETE` needs the session's
CSRF token in `X-CSRF-Token` (from the sign-in response or `GET /v1/me`; keep it
in memory, not browser storage). Credentialed CORS is allowed only from
`WEB_ORIGIN`. Five failed password or TOTP attempts lock the account for 15
minutes, and all sign-in errors are the same generic `unauthenticated`.

**Deprecated:** `/orgs/{org_id}/households`, `/orgs/{org_id}/cases` and `/me`
still work (cookie or dev bearer) and return `Deprecation: true` plus a `Link`
to the `/v1` route. They will be removed once the deployed clients move.

**Development only:** `POST /auth/login` exchanges a seeded user's password for a
JWT bearer token, accepted by `/v1` and the legacy routes. It is not mounted in
production, and bearer tokens are rejected there.

```bash
TOKEN=$(curl -s localhost:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"ana@aguazul.org","password":"local-demo-pass"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8000/v1/me -H "authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/v1/households \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{"reference_code":"DEMO-1","estimated_member_count":4,
       "needs":[{"category":"water_delivery","requested_quantity":40,"unit":"liters"}]}'
curl -s localhost:8000/v1/cases -H "authorization: Bearer $TOKEN"
```

Locally, the seeded demo users can also use the real cookie flow: outside
production, the first `POST /v1/auth/password/login` with the seed password
adopts it as an Argon2id credential, then TOTP enrollment is required as usual.

With more than one membership, a dev bearer caller can pick the org with
`X-Org-Id` (checked against its memberships).

Password and TOTP credentials, sessions and OIDC flows are kept behind the
`AuthStore` interface (`app/auth/store.py`). Until the database tables exist it
is **in memory**: sessions are lost on restart and not shared between
instances, so run a single instance.

### Tests

```bash
.venv/bin/python -m pytest
```

Covered: password + TOTP and Google OIDC sign-in, session timeouts, CSRF/CORS,
revocation, `/v1` and legacy routes, the error envelope, rate limits, a log scan
for seeded personal data, assisted intake (household + contacts + assessment + case + needs
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

Redeploy after code changes. Commit first, then run from this directory:

```bash
npm run deploy          # build image, run migrations, roll out new revision, print URL
npm run deploy:verify   # synthetic smoke tests
```

`npm run deploy:service` only rolls out a new revision, for example after a secret
changes. `npm run deploy:url` prints the URLs. There are no JS dependencies, so no
`npm install` is needed.

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

- **One APIRouter per endpoint group.** Implemented: `auth`, `me`, `admin`,
  `households`, `cases`, `webhooks`, `health`. The fulfillment stubs (`water`,
  `charging`) are removed; `reviews` is an unmounted placeholder.
- **Tenant isolation.** `/v1` routes use `get_v1_context` (`app/deps.py`): the
  org is the session's active organization, re-checked against an active
  membership on every request. Legacy `/orgs/{org_id}/...` routes use
  `get_org_context`, which checks the path org against memberships. Either way
  the result is a `RequestContext(org_id, actor_id, membership_id, role)`, the
  org never comes from the request body, and a non-member or cross-org row
  returns **404** (not 403) so existence is not leaked.
- **Domain layer** (`app/domain/`) functions take `(ctx, db, ...)`, scope every
  query to `ctx.org_id`, and contain no HTTP concerns. Intake runs in one
  transaction.
- **Structured errors** (`app/errors.py`, CON-040): every error is
  `{"code", "message_key", "details", "request_id"}`. Codes: `validation_failed`,
  `unauthenticated`, `forbidden`, `not_found`, `conflict`, `idempotency_conflict`,
  `rate_limited`, `internal_error`, and the other CON-040 codes. Validation
  details keep only `loc` and `type`, never the submitted input.
- **Request IDs and logs**: every response carries `X-Request-ID` (a
  well-formed client value is reused). Logs are JSON with route templates, never
  bodies, query strings or exception messages, behind a redaction filter
  (`app/auth/logs.py`). Sensitive responses are `Cache-Control: no-store`.
- **Idempotency** (`app/idempotency.py`): `Idempotency-Key` stores the first
  result per `(org, endpoint, key)` with a digest of the request body and the
  actor. A retry with the same body replays it; a different body or actor gets
  409 `idempotency_conflict`.
- **Rate limits** (`app/auth/ratelimit.py`): per client IP on every sign-in step
  and on the webhook, in process.
- **Webhooks** (`app/routers/webhooks.py`): `GET /webhooks/whatsapp` does the Meta
  handshake; `POST` verifies `X-Hub-Signature-256`, persists the raw payload to
  `inbound_event`, and returns 200 immediately. No LLM calls or outbound sends in
  the request. A separate worker (not in this deliverable) polls unprocessed
  `inbound_event` rows — see `components/worker`.

## Environment variables

See `.env.example`. `DATABASE_URL`, `JWT_SECRET`, and the WhatsApp secrets
(`WHATSAPP_TOKEN`, `APP_SECRET`, `VERIFY_TOKEN`, `PHONE_NUMBER_ID`) come from the
environment / `.env`. Never commit `.env`.

Staff auth settings (all optional; defaults in `app/config.py`):

| Variable | Default | Notes |
|----------|---------|-------|
| `WEB_ORIGIN` | empty | Web app origin, e.g. `https://app.example.org`. Enables credentialed CORS and the `Origin` check; OIDC redirects go here. Must be https in production. |
| `SESSION_COOKIE_SECURE` | `true` | Set `false` only for plain-http local dev. Production refuses `false`. |
| `SESSION_COOKIE_DOMAIN` | empty | Leave empty to get a host-only `__Host-` cookie. |
| `OIDC_GOOGLE_CLIENT_ID`, `OIDC_GOOGLE_CLIENT_SECRET`, `OIDC_GOOGLE_REDIRECT_URI` | empty | All three enable Google sign-in. The redirect URI is `https://<api host>/v1/auth/oidc/google/callback`. |
| `SESSION_IDLE_TIMEOUT_MINUTES`, `SESSION_ABSOLUTE_TIMEOUT_HOURS` | 30, 12 | SEC-05 |
| `PASSWORD_MAX_FAILURES`, `PASSWORD_LOCKOUT_MINUTES` | 5, 15 | |
| `RATE_LIMIT_SIGNIN_PER_MINUTE`, `RATE_LIMIT_WEBHOOK_PER_MINUTE` | 10, 1200 | Per client IP |
| `FORWARDED_FOR_TRUSTED_HOPS` | 0 | Set `1` behind Cloud Run so limits key on the client IP |
| `JSON_LOGS`, `LOG_LEVEL` | `true`, `INFO` | |

The web app and the API must share a registrable domain (for example
`app.example.org` and `api.example.org`): `SameSite=Lax` cookies are not sent on
cross-site requests.

## Layout

```
app/
  main.py          FastAPI app, router mounting, error handlers
  config.py        Settings from env/.env
  db.py            Engine, session, get_db dependency
  security.py      Development-only JWT bearer login (+ legacy bcrypt hash)
  deps.py          get_principal, get_v1_context, get_org_context, require_role
  auth/            Sessions, password + TOTP, Google OIDC, auth store,
                   rate limits, request-ID middleware, redacted logging
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
