# Dashboard API

FastAPI service that powers the web dashboard. It **reads the shared database
written by `whatsapp/api`** (reports, orgs, needs, observations) and manages
org-level dashboard settings. It creates **no tables and runs no migrations** —
it reuses whatsapp/api's SQLAlchemy models via a runtime bridge
([`dash/shared_db.py`](dash/shared_db.py)).

- Package: `dash` (named to avoid colliding with whatsapp/api's `app` package).
- Auth: JWT bearer, **same scheme and shared `JWT_SECRET`** as whatsapp/api, so a
  token from either service works on both. Org always comes from the token's
  membership — never the request body.
- Data model: **report-centric** (cases are deferred in the pilot).
- Contract: [CONTRACT.md](CONTRACT.md) + checked-in [openapi.json](openapi.json).

## Run locally

```bash
cd components/api
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"

# Point at the shared DB and make sure its schema is migrated (run once, from
# whatsapp/api, if you haven't):
#   (cd ../whatsapp/api && .venv/bin/alembic upgrade head)

export DATABASE_URL="sqlite:///../whatsapp/api/local-data/aid.sqlite3"

# Seed ~80 Miami reports (12 urgent) for a full-looking demo:
.venv/bin/python -m scripts.seed_miami

.venv/bin/uvicorn dash.main:app --reload --port 8001
```

- Docs: http://127.0.0.1:8001/docs
- Demo login: `demo@metron.org` / `demo-pass`

## Tests

```bash
export DATABASE_URL="sqlite:///../whatsapp/api/local-data/aid.sqlite3"
.venv/bin/python -m pytest
```

## Deploy (Cloud Run)

Same project / DB / secrets as whatsapp/api. The image bundles both trees, so it
builds with the context at `components/`:

```bash
cd components/api
./deploy/gcloud-deploy.sh deploy     # build + grant + service + url
```

See [deploy/gcloud-deploy.sh](deploy/gcloud-deploy.sh). It reuses the shared
`database-url` and `jwt-secret` Secret Manager secrets and the `webhook-run`
runtime service account.

## Real vs. mocked (Step 2 status)

| Endpoint group | Status |
|---|---|
| `auth` (signup/login/me) | **Real** — users/orgs/memberships in the shared DB |
| `dashboard` summary / areas / feed | **Real** — aggregated from `report` / `observation` / `need` |
| `reports` list / get / patch | **Real** — report-centric, org-scoped |
| `org` profile / data-protection / channels / bot-config / dashboard-config | **Real & durable** — stored in `policy_version` (survives restart) |
| `templates/*` (collection, dashboard, recommended) | **Static** — curated template catalog (by design) |
| `contacts` list / import | **Mocked** — no contact table in the intake schema yet |
| `campaigns` | **Mocked** — create/list in memory |
| `/ask` | **Mocked** — canned NL answer |

Report rows carry **no decryptable PII** (reporter names are encrypted at rest in
the intake schema and not decoded here), so name/phone come back `null`;
data-protection masking is demonstrated on `/contacts`.
