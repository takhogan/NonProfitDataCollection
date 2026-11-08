# Aid coordination platform

A **data aggregation platform** for Venezuela. It collects reports of power and water
cuts and of household needs, and turns them into area-level indicators. Providers
(NGOs, water distributors, charging hosts) log in, see which areas need help and which
are uncovered, and act with their own resources. It is not an aid dispatch system.
Residents report through "Metron Reporter" on WhatsApp. The first operating NGO is
Ciudadanía Sin Límites in Caracas.

## Current state

This repository contains the product plan, the requirements, and these runnable components:

- [`components/whatsapp/api`](components/whatsapp/api/README.md): the FastAPI backend
  (staff API, WhatsApp webhook) and the background worker. PostgreSQL/PostGIS with RLS.
  The webhook is live on Cloud Run with a real number.
- [`components/api`](components/api/README-DASHBOARD.md): the dashboard API (`dash`),
  which reads the same database through the backend's models.
- [`components/web`](components/web/README.md): the Metron React/TypeScript/Vite frontend
  (mock API by default), live as Cloud Run `metron-web` behind
  https://metron-reporter.web.app, and the Firebase Hosting config.

- [Product plan and logical schema](PLATFORM_PLAN.md)
- [Component stacks, boundaries, and implementation roadmap](components/README.md)
- [Requirements: pilot context, roles, threat model, and per-component features](components/REQUIREMENTS.md)

The first release serves one NGO while enforcing organization ownership in the
data model. Later releases add explicit referrals and controlled collaboration
between organizations.

## Running locally

One command starts everything. It needs Docker running, Python 3.11 or newer, and
Node 24.22 or newer (`nvm use` reads `.nvmrc`). It has no npm dependencies, so no
`npm install` is needed at the root.

```bash
nvm use
npm run start:dev
```

[`scripts/dev.mjs`](scripts/dev.mjs) does this, in order:

1. Checks the prerequisites and that ports 8000, 8001 and 5173 are free.
2. Runs `docker compose up -d db` in `components/whatsapp/api` (PostGIS on
   `localhost:55432`) and waits until it is healthy.
3. Copies `components/whatsapp/api/.env.postgres.example` to `.env` if there is no
   `.env`. An existing `.env` is never overwritten.
4. Creates `.venv` in `components/whatsapp/api` and `components/api` if missing, and
   runs `pip install -e ".[dev]"` again whenever `pyproject.toml` changed. Runs
   `npm ci` in `components/web` if `node_modules` is missing.
5. Creates the database named in `DATABASE_URL` if it does not exist, then runs
   `alembic upgrade head`.
6. Seeds synthetic data: `python -m scripts.seed` (Caracas demo orgs) and the
   dashboard's `python -m scripts.seed_miami` (`demo@metron.org` / `demo-pass`). Both
   skip what already exists, so they are safe on every run.
7. Starts four processes with coloured, prefixed output:

| Prefix | Process | URL |
|---|---|---|
| `api` | backend, `uvicorn app.main:app --reload` | http://localhost:8000/health, `/docs` |
| `worker` | `python -m scripts.worker` (fake WhatsApp adapter, sends nothing) | none |
| `dashboard` | dashboard API, `uvicorn dash.main:app --reload --port 8001` | http://localhost:8001/docs |
| `web` | `npm run dev` (Vite) | http://localhost:5173 |

Ctrl-C stops all four, including the reloader children. If one process exits on its
own, the others are stopped too. A second Ctrl-C kills them at once.

| Option | Effect |
|---|---|
| `npm run start:dev -- --web=http` (or `DEV_WEB_MODE=http`) | Web app uses the local dashboard API: `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8001` (override by exporting it). Log in as `demo@metron.org` / `demo-pass`. The default is the in-memory mock client. |
| `npm run start:dev -- --no-seed` (or `DEV_SKIP_SEED=1`) | Skip both seed scripts. |
| `npm run setup:dev` | Do steps 1 to 6 and exit (no ports needed). |
| `PYTHON=python3.12 npm run start:dev` | Interpreter used to create missing venvs. |

**One database for everything.** The dashboard API runs against the same Postgres
database as the backend (`DATABASE_URL` and `JWT_SECRET` are read from
`components/whatsapp/api/.env`). This works locally because the connection is the
`postgres` superuser, which bypasses RLS: the dashboard filters by
`organization_id` in code and does not switch roles. The SQLite path in
`README-DASHBOARD.md` is still valid for running the dashboard on its own.

**Worktrees.** Every checkout shares one Postgres container and volume: the compose
project is named after the folder, `api`. Branches can change migrations under the
same revision id, so when `.env` is first created inside `.claude/worktrees/<name>`,
the database is `csl_dev_<name>`, not `csl_dev`. To use another database, edit
`DATABASE_URL` in `.env`. It is created on the next start.

**Resetting.** Drop the database and start again, for example
`docker exec api-db-1 psql -U postgres -c 'DROP DATABASE csl_dev_<name>'`. To wipe the
whole volume, use `docker compose down -v` in `components/whatsapp/api`. That wipes every
checkout's database.

### Tests

```bash
# backend (needs the Docker db; without TEST_POSTGRES_URL the Postgres tests skip)
cd components/whatsapp/api
TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres-local-only@localhost:55432/postgres .venv/bin/python -m pytest

# dashboard API: reads the seeded demo org; point it at the dev database
cd components/api
DATABASE_URL="$(grep ^DATABASE_URL= ../whatsapp/api/.env | cut -d= -f2-)" .venv/bin/python -m pytest

# web
cd components/web && npm test
```

## Deploying

Deploys go to the **live** GCP project `csl-metron-webhook`: Cloud Run, Cloud SQL,
and a WhatsApp number that real people message. Run them deliberately, from a clean
tree (images are tagged with the commit hash).

```bash
npm run deploy -- --dry-run     # preflight + plan + the exact commands; runs nothing
npm run deploy                  # api, then dashboard, then web, then site
npm run deploy:api              # one target (deploy:dashboard, deploy:web, deploy:site)
```

[`scripts/deploy.sh`](scripts/deploy.sh) checks first: a clean `components/`, an
active gcloud account that can read the project, and, for `site`, the `firebase` CLI
and that `components/web/static-site/` holds only `.html`/`.css`. It prints the image tag that
is live on each Cloud Run service and how many files changed since then. Then it asks
you to type `deploy` (`--yes` skips this; without a terminal it refuses unless `--yes`).

| Target | What runs | Notes |
|---|---|---|
| `api` | `components/whatsapp/api/deploy/gcloud-deploy.sh deploy` | Cloud Build image, then the `aid-migrate` Cloud Run job runs `alembic upgrade head` and waits, then the `whatsapp-webhook` service. See [DEPLOY.md](components/whatsapp/api/DEPLOY.md). The worker service (`aid-worker`) is **not** deployed; it is not approved yet. |
| `dashboard` | `gcloud builds submit --config components/cloudbuild.dashboard.yaml`, then `components/api/deploy/gcloud-deploy.sh grant service url` with `SERVICE=metron-api` | Cloud Run `metron-api`, same image tag. `WEB_ORIGINS` (CORS) is set by `scripts/deploy.sh`. That script's own `build` step does not work: `gcloud builds submit` has no `-f` flag. Runs after `api` because it reads the schema the api migrates. |
| `web` | `gcloud run deploy metron-web --source .` in `components/web` | The Metron frontend: [Dockerfile](components/web/Dockerfile) builds Vite against `metron-api` and serves it with nginx. |
| `site` | `firebase deploy --only hosting` in `components/web` | https://metron-reporter.web.app: `/privacidad` (Meta's privacy URL) is static, everything else is rewritten to `metron-web`. See [HOSTING.md](components/web/HOSTING.md). |

Targets always run in the order api, dashboard, web, site. Nothing is skipped
automatically, because "unchanged since the last deploy" cannot be decided reliably:
live tags can be commits from other branches, and the dashboard image bundles the
backend. Use the preflight's change count to decide which targets to name.

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

Hosting: Google Cloud Run and Cloud SQL (PostgreSQL) in `us-east4` (Virginia), GCP
project `csl-metron-webhook`, and Firebase Hosting in front (metron-reporter.web.app). See
[Deploying](#deploying). (The earlier plan was Render.)

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
