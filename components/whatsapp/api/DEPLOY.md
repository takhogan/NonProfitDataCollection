# Deploying to Google Cloud Run

This deploys the aid-coordination API and its background worker to Cloud Run
from a single container image, with PostgreSQL on Cloud SQL and all secrets in
Secret Manager. Migrations run as a **separate** Cloud Run Job (never on
container start).

Architecture:

```
                 ┌──────────────┐
  Meta WhatsApp → │  api (Run)   │ ──┐
  Staff browser → │  HTTP :8080  │   │
                 └──────────────┘   │        ┌─────────────┐
                 ┌──────────────┐   ├──────→ │  Cloud SQL  │
                 │ worker (Run) │ ──┘        │ PostgreSQL  │
                 │ no HTTP port │            └─────────────┘
                 └──────────────┘
  migrate/seed = one-off Cloud Run Jobs (same image, different command)
```

All three (api, worker, migrate-job) are the **same image**; they differ only in
the command they run.

---

## 0. Prerequisites and variables

Install the `gcloud` CLI and authenticate:

```bash
gcloud auth login
```

Set these shell variables (edit the first three):

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export DB_PASSWORD="$(openssl rand -base64 24)"   # Cloud SQL app-user password

export REPO="aid"                                  # Artifact Registry repo
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/aid-api:latest"
export SQL_INSTANCE="aid-pg"
export DB_NAME="aid"
export DB_USER="aid_app"

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

> Run every command below from this directory (`components/whatsapp/api`), since
> the build uses the `Dockerfile` here.

---

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com
```

---

## 2. Create the Artifact Registry repo and build the image

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Aid coordination images"

# Build with Cloud Build and push to Artifact Registry.
gcloud builds submit --tag "$IMAGE" .
```

---

## 3. Create the Cloud SQL (PostgreSQL) instance, database, and user

```bash
gcloud sql instances create "$SQL_INSTANCE" \
  --database-version=POSTGRES_15 \
  --edition=enterprise \
  --tier=db-f1-micro \
  --region="$REGION"

gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

gcloud sql users create "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --password="$DB_PASSWORD"

# Full instance connection name, e.g. your-project:us-central1:aid-pg
export SQL_CONN="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --format='value(connectionName)')"
echo "SQL_CONN=$SQL_CONN"
```

The app connects over the Cloud SQL unix socket that Cloud Run mounts at
`/cloudsql/<SQL_CONN>`, so `DATABASE_URL` is:

```bash
export DATABASE_URL="postgresql+psycopg://$DB_USER:$DB_PASSWORD@/$DB_NAME?host=/cloudsql/$SQL_CONN"
```

---

## 4. Create secrets in Secret Manager

Generate app secrets and store everything. `VERIFY_TOKEN` is any string you also
paste into Meta; `APP_SECRET`/`WHATSAPP_TOKEN`/`PHONE_NUMBER_ID` come from the
Meta WhatsApp app.

```bash
# Generate strong values where we control them.
printf '%s' "$(openssl rand -hex 32)"       | gcloud secrets create jwt-secret           --data-file=-
printf '%s' "$(openssl rand -hex 16)"       | gcloud secrets create verify-token         --data-file=-
printf '%s' "$(openssl rand -base64 18)"    | gcloud secrets create seed-demo-password   --data-file=-
printf '%s' "$DATABASE_URL"                 | gcloud secrets create database-url          --data-file=-

# From the Meta WhatsApp app (paste the real values).
printf '%s' "PASTE_META_APP_SECRET"         | gcloud secrets create whatsapp-app-secret  --data-file=-
printf '%s' "PASTE_META_PERMANENT_TOKEN"    | gcloud secrets create whatsapp-token       --data-file=-
printf '%s' "PASTE_META_PHONE_NUMBER_ID"    | gcloud secrets create whatsapp-phone-id    --data-file=-
```

Grant the Cloud Run runtime service account access to read them:

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export RUN_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

for S in jwt-secret verify-token seed-demo-password database-url \
         whatsapp-app-secret whatsapp-token whatsapp-phone-id; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:$RUN_SA" \
    --role="roles/secretmanager.secretAccessor"
done

# The same SA needs to connect to Cloud SQL.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/cloudsql.client"
```

> We map secrets to the exact env var names the app expects:
> `DATABASE_URL`, `JWT_SECRET`, `APP_SECRET`, `WHATSAPP_TOKEN`,
> `PHONE_NUMBER_ID`, `VERIFY_TOKEN`, `SEED_DEMO_PASSWORD`. With
> `APP_ENV=production`, startup **fails fast** if any are missing or still set to
> an insecure placeholder.

A reusable flag list (used by every deploy/job command below):

```bash
export SECRET_FLAGS="--set-secrets=\
DATABASE_URL=database-url:latest,\
JWT_SECRET=jwt-secret:latest,\
VERIFY_TOKEN=verify-token:latest,\
SEED_DEMO_PASSWORD=seed-demo-password:latest,\
APP_SECRET=whatsapp-app-secret:latest,\
WHATSAPP_TOKEN=whatsapp-token:latest,\
PHONE_NUMBER_ID=whatsapp-phone-id:latest"
```

---

## 5. Run migrations (separate step — Cloud Run Job)

Migrations are **not** run on container start (concurrent instances would race
on DDL). Run them once per deploy as a job using the same image with a different
command.

```bash
gcloud run jobs create aid-migrate \
  --image="$IMAGE" \
  --region="$REGION" \
  --set-cloudsql-instances="$SQL_CONN" \
  --set-env-vars=APP_ENV=production \
  $SECRET_FLAGS \
  --command=python \
  --args=-m,scripts.migrate

# Execute it (re-run after each deploy that adds migrations):
gcloud run jobs execute aid-migrate --region="$REGION" --wait
```

On later deploys, update and re-run instead of re-creating:

```bash
gcloud run jobs update aid-migrate --image="$IMAGE" --region="$REGION"
gcloud run jobs execute aid-migrate --region="$REGION" --wait
```

---

## 6. Seed demo data (one-off Cloud Run Job)

Optional, for the demo. Idempotent: it skips if organizations already exist.

```bash
gcloud run jobs create aid-seed \
  --image="$IMAGE" \
  --region="$REGION" \
  --set-cloudsql-instances="$SQL_CONN" \
  --set-env-vars=APP_ENV=production \
  $SECRET_FLAGS \
  --command=python \
  --args=-m,scripts.seed

gcloud run jobs execute aid-seed --region="$REGION" --wait
```

The demo login password is whatever you stored in `seed-demo-password`:

```bash
gcloud secrets versions access latest --secret=seed-demo-password; echo
```

Demo logins: `ana@aguazul.org`, `luis@aguazul.org`, `maria@luzviva.org`.

---

## 7. Deploy the API service

```bash
gcloud run deploy aid-api \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --set-cloudsql-instances="$SQL_CONN" \
  --set-env-vars=APP_ENV=production \
  $SECRET_FLAGS
```

The container's default command serves `uvicorn app.main:app` on `$PORT`
(Cloud Run sets `$PORT=8080`). Grab the URL:

```bash
export API_URL="$(gcloud run services describe aid-api --region="$REGION" \
  --format='value(status.url)')"
echo "API_URL=$API_URL"

curl -s "$API_URL/health"            # {"status":"ok"}
```

---

## 8. Deploy the worker service (same image, different command)

The worker polls the `inbound_event` inbox continuously, so it must keep a
warm instance and not have its CPU throttled between requests:

```bash
gcloud run deploy aid-worker \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --no-allow-unauthenticated \
  --min-instances=1 \
  --no-cpu-throttling \
  --set-cloudsql-instances="$SQL_CONN" \
  --set-env-vars=APP_ENV=production \
  $SECRET_FLAGS \
  --command=python \
  --args=-m,scripts.worker
```

Notes:
- `--min-instances=1` keeps the poller alive (no cold starts dropping the loop).
- `--no-cpu-throttling` lets the loop run between HTTP requests (the worker has
  no HTTP traffic, so without this its CPU would be throttled to near zero).
- `--no-allow-unauthenticated`: the worker exposes no public surface.

---

## 9. Point Meta at the webhook

The webhook URL to paste into the Meta WhatsApp app's webhook configuration is
the API URL plus `/webhooks/whatsapp`:

```bash
echo "$API_URL/webhooks/whatsapp"
```

In the Meta app dashboard → WhatsApp → Configuration → Webhook:
- **Callback URL:** `<API_URL>/webhooks/whatsapp`
- **Verify token:** the value stored in the `verify-token` secret:
  ```bash
  gcloud secrets versions access latest --secret=verify-token; echo
  ```

Meta sends a `GET` with `hub.mode`, `hub.verify_token`, `hub.challenge`; the API
echoes the challenge when the token matches. Then subscribe to the **messages**
field so inbound messages and delivery statuses `POST` to the same URL. Each
event's `X-Hub-Signature-256` is verified against the `APP_SECRET`; accepted
events are persisted to `inbound_event` before a `200` is returned, and the
worker processes them asynchronously.

---

## 10. Redeploy workflow (subsequent changes)

```bash
gcloud builds submit --tag "$IMAGE" .                       # 1. rebuild
gcloud run jobs update aid-migrate --image="$IMAGE" --region="$REGION"
gcloud run jobs execute aid-migrate --region="$REGION" --wait   # 2. migrate
gcloud run deploy aid-api    --image="$IMAGE" --region="$REGION"  # 3. api
gcloud run deploy aid-worker --image="$IMAGE" --region="$REGION" \
  --command=python --args=-m,scripts.worker                       # 4. worker
```

## Troubleshooting

- **API/worker crash-loops on boot with a config error** — that is the
  fail-fast guard: a required secret is missing or still a placeholder. Check
  `gcloud run services logs read aid-api --region=$REGION`; the error names the
  offending variables.
- **`sqlite` rejected in production** — `DATABASE_URL` must be the Postgres URL.
  Confirm the `database-url` secret resolved and `APP_ENV=production` is set.
- **Cloud SQL connection refused** — verify `--set-cloudsql-instances="$SQL_CONN"`
  is on the service/job and the runtime SA has `roles/cloudsql.client`.
```
