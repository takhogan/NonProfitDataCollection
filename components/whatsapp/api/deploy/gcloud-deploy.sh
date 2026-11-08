#!/usr/bin/env bash
# Deploy the WhatsApp webhook (FastAPI app) to Cloud Run in its own GCP project.
#
#   deploy/gcloud-deploy.sh <step>      # run one step
#   deploy/gcloud-deploy.sh all         # run every step in order (new project)
#   deploy/gcloud-deploy.sh deploy      # redeploy code: build migrate service url
#
# Steps: project apis registry build sql sa secrets migrate service url
#
# Every step is safe to re-run (it skips what already exists), except `build`,
# `migrate` and `service`, which roll out a new image/revision each time.
#
# Secrets: values are generated here or read from stdin and piped straight into
# Secret Manager. They never touch the repo, the image, or command-line flags,
# except the Cloud SQL user password, which `gcloud sql users create` only takes
# as a flag (local process list only; rotate with `sql users set-password`).
#
# Run from components/whatsapp/api (the build context).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-csl-metron-webhook}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-01661D-983EDC-7A0067}"
REGION="${REGION:-us-east4}"            # Virginia: outside Venezuela, per hosting plan
SERVICE="${SERVICE:-whatsapp-webhook}"
REPO="${REPO:-aid}"
SQL_INSTANCE="${SQL_INSTANCE:-aid-pg}"
DB_NAME="${DB_NAME:-aid}"
DB_USER="${DB_USER:-aid_app}"
RUN_SA_NAME="${RUN_SA_NAME:-webhook-run}"

IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/aid-api:$IMAGE_TAG"
RUN_SA="$RUN_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Secret Manager name -> env var the app reads (see app/config.py).
SECRET_MAP=(
  "database-url:DATABASE_URL"
  "jwt-secret:JWT_SECRET"
  "verify-token:VERIFY_TOKEN"
  "whatsapp-app-secret:APP_SECRET"
  "whatsapp-token:WHATSAPP_TOKEN"
  "whatsapp-phone-id:PHONE_NUMBER_ID"
  "seed-demo-password:SEED_DEMO_PASSWORD"
)

g() { gcloud --project="$PROJECT_ID" --quiet "$@"; }

secret_flags() {
  local out="" pair
  for pair in "${SECRET_MAP[@]}"; do
    out+="${pair#*:}=${pair%%:*}:latest,"
  done
  echo "--set-secrets=${out%,}"
}

sql_conn() { g sql instances describe "$SQL_INSTANCE" --format='value(connectionName)'; }

step_project() {
  if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud projects create "$PROJECT_ID" --name="CSL Metron webhook"
  fi
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
}

step_apis() {
  # Only what this deployment uses.
  g services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    iam.googleapis.com
}

step_registry() {
  g artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 ||
    g artifacts repositories create "$REPO" --repository-format=docker \
      --location="$REGION" --description="Aid coordination images"
}

step_build() {
  g builds submit --region="$REGION" --tag "$IMAGE" .
}

step_sql() {
  if ! g sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
    # Smallest shared-core tier. Public IP but NO authorized networks: the only
    # way in is the IAM-authorized Cloud SQL connector Cloud Run uses.
    g sql instances create "$SQL_INSTANCE" \
      --database-version=POSTGRES_16 --edition=enterprise --tier=db-f1-micro \
      --region="$REGION" --storage-type=SSD --storage-size=10GB \
      --storage-auto-increase --backup-start-time=07:00 \
      --require-ssl --deletion-protection
  fi
  g sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1 ||
    g sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

  if ! g sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$DB_USER"; then
    local pw conn
    pw="$(openssl rand -hex 24)"
    g sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$pw"
    conn="$(sql_conn)"
    # DATABASE_URL goes straight to Secret Manager; it is never printed.
    put_secret database-url <<<"postgresql+psycopg://$DB_USER:$pw@/$DB_NAME?host=/cloudsql/$conn"
  fi
}

step_sa() {
  g iam service-accounts describe "$RUN_SA" >/dev/null 2>&1 ||
    g iam service-accounts create "$RUN_SA_NAME" --display-name="WhatsApp webhook runtime"
  # Project-level: connect to Cloud SQL only. Secret access is per secret.
  g projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUN_SA" --role="roles/cloudsql.client" \
    --condition=None >/dev/null
}

# put_secret NAME  (value on stdin) -- creates the secret or adds a version.
put_secret() {
  local name="$1"
  if g secrets describe "$name" >/dev/null 2>&1; then
    g secrets versions add "$name" --data-file=- >/dev/null
  else
    g secrets create "$name" --replication-policy=user-managed \
      --locations="$REGION" --data-file=- >/dev/null
  fi
  echo "secret $name: stored"
}

# ensure_secret NAME  (value on stdin) -- only if the secret doesn't exist yet.
ensure_secret() {
  if g secrets describe "$1" >/dev/null 2>&1; then cat >/dev/null; echo "secret $1: exists"; else put_secret "$1"; fi
}

step_secrets() {
  openssl rand -hex 32 | tr -d '\n' | ensure_secret jwt-secret
  openssl rand -hex 24 | tr -d '\n' | ensure_secret verify-token
  openssl rand -hex 24 | tr -d '\n' | ensure_secret seed-demo-password
  # Meta-owned values. Until davidkim1 adds real versions, APP_SECRET is a random
  # synthetic value (so only our own test requests verify) and the outbound
  # token/phone id are placeholders (nothing sends from this service yet).
  openssl rand -hex 32 | tr -d '\n' | ensure_secret whatsapp-app-secret
  printf 'unset-replace-with-meta-token' | ensure_secret whatsapp-token
  printf 'unset-replace-with-phone-number-id' | ensure_secret whatsapp-phone-id

  local pair
  for pair in "${SECRET_MAP[@]}"; do
    g secrets add-iam-policy-binding "${pair%%:*}" \
      --member="serviceAccount:$RUN_SA" \
      --role="roles/secretmanager.secretAccessor" >/dev/null
  done
}

step_migrate() {
  local verb=create
  g run jobs describe aid-migrate --region="$REGION" >/dev/null 2>&1 && verb=update
  g run jobs "$verb" aid-migrate --region="$REGION" --image="$IMAGE" \
    --service-account="$RUN_SA" \
    --set-cloudsql-instances="$(sql_conn)" \
    --set-env-vars=APP_ENV=production "$(secret_flags)" \
    --command=python --args=-m,scripts.migrate \
    --max-retries=0 --task-timeout=10m
  g run jobs execute aid-migrate --region="$REGION" --wait
}

step_service() {
  # Public because Meta must reach /webhooks/whatsapp; HMAC signature
  # verification (APP_SECRET) is what authenticates POSTs.
  g run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" \
    --service-account="$RUN_SA" \
    --allow-unauthenticated --port=8080 \
    --min-instances=0 --max-instances=3 --cpu=1 --memory=512Mi \
    --set-cloudsql-instances="$(sql_conn)" \
    --set-env-vars=APP_ENV=production "$(secret_flags)"
}

step_url() {
  local url
  url="$(g run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
  echo "Service URL:  $url"
  echo "Webhook URL:  $url/webhooks/whatsapp"
}

# Redeploy the current commit. Refuses a dirty tree, because the image is
# tagged with the commit hash and must match what was built.
step_deploy() {
  if [[ -n "$(git status --porcelain -- . 2>/dev/null)" ]]; then
    echo "Uncommitted changes in $(pwd); commit or stash them first." >&2
    exit 1
  fi
  for s in build migrate service url; do echo "== $s"; "step_$s"; done
}

main() {
  local s="${1:-}"
  case "$s" in
    deploy) step_deploy ;;
    all) for s in project apis registry build sql sa secrets migrate service url; do
           echo "== $s"; "step_$s"; done ;;
    project|apis|registry|build|sql|sa|secrets|migrate|service|url) "step_$s" ;;
    *) sed -n '2,17p' "$0"; exit 1 ;;
  esac
}

main "$@"
