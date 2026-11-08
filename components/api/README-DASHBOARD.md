# Dashboard API — run & implementation notes

This is the running **dashboard** service for the web frontend. It reads the
shared database written by [`whatsapp/api`](../whatsapp/api/README.md) and manages
org settings. Report-centric (cases are deferred in the pilot, per
[README.md](README.md)).

> The planning doc for this component is [README.md](README.md) +
> [REQUIREMENTS.md](REQUIREMENTS.md). **The frontend contract is
> [CONTRACT.md](CONTRACT.md)** (every endpoint + example responses).

## Status

**Step 1 (contract-first) — done.** All routes return realistic fake data; shapes
are stable. **Step 2** swaps fake data for real queries against the shared DB (no
new tables/migrations — it imports `whatsapp/api`'s SQLAlchemy models).

## Run locally

```bash
cd components/api
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8001
```

- Docs: http://localhost:8001/docs · OpenAPI: `/openapi.json` (checked in as
  [openapi.json](openapi.json))
- Health: http://localhost:8001/health
- Demo login: `demo@metron.org` / `demo-pass`

```bash
TOKEN=$(curl -s localhost:8001/auth/login -H 'content-type: application/json' \
  -d '{"email":"demo@metron.org","password":"demo-pass"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s localhost:8001/dashboard/summary -H "authorization: Bearer $TOKEN"
```

## Design rules enforced

- **Org from the JWT membership**, never the request body; every query org-scoped.
- **Data protection enforced in the API**: `/org/data-protection` settings mask
  phones, omit names, and drop precise location *before* serialization, so the UI
  cannot leak them. (Verified: flipping the preset changes `/reports` and
  `/contacts` output.)
- **Same JWT scheme as `whatsapp/api`** (`JWT_SECRET` must match).
- **CORS** restricted to `WEB_ORIGINS`.

## Config (env / `.env`)

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | shared SQLite path | Step 2: shared Postgres |
| `JWT_SECRET` | `change-me-dev-only` | **Must match `whatsapp/api`** |
| `WEB_ORIGINS` | `http://localhost:5173,http://localhost:3000` | credentialed CORS |

## No schema conflicts

This service adds **no tables and no migrations**. It reuses `whatsapp/api`'s
models (Step 2, by import) and writes only to the fake in-memory store today.
