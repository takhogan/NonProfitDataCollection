#!/usr/bin/env bash
# Deploy the dashboard API to Cloud Run, in the SAME project and sharing the
# SAME database + JWT secret as the whatsapp/api webhook (so logins and data are
# interoperable). The dashboard creates no tables and runs no migrations.
#
#   deploy/gcloud-deploy.sh <step>     # one step
#   deploy/gcloud-deploy.sh deploy     # build + service + url
#
# Steps: registry build service url
#
# Run from components/api. The image is built with the context at components/
# (the parent) because the dashboard image bundles whatsapp/api too.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-csl-metron-webhook}"
REGION="${REGION:-us-east4}"
SERVICE="${SERVICE:-metron-api}"
REPO="${REPO:-aid}"
SQL_INSTANCE="${SQL_INSTANCE:-aid-pg}"
RUN_SA_NAME="${RUN_SA_NAME:-webhook-run}"           # reuse the webhook runtime SA
WEB_ORIGINS="${WEB_ORIGINS:-https://dashboard.example.org,http://localhost:5173}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"         # model for campaign-field suggestions

IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/dashboard-api:$IMAGE_TAG"
RUN_SA="$RUN_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Shared secrets already created by whatsapp/api's deploy. The dashboard reads
# the SAME database-url and jwt-secret so tokens and data interoperate.
# openai-api-key is this service's own secret (create it before deploying; see
# deploy/README or the secret-creation commands handed over with this change).
SECRET_MAP=(
  "database-url:DATABASE_URL"
  "jwt-secret:JWT_SECRET"
  "openai-api-key:OPENAI_API_KEY"
)

g() { gcloud --project="$PROJECT_ID" --quiet "$@"; }

secret_flags() {
  local out="" pair
  for pair in "${SECRET_MAP[@]}"; do out+="${pair#*:}=${pair%%:*}:latest,"; done
  echo "--set-secrets=${out%,}"
}

sql_conn() { g sql instances describe "$SQL_INSTANCE" --format='value(connectionName)'; }

step_registry() {
  g artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 ||
    g artifacts repositories create "$REPO" --repository-format=docker \
      --location="$REGION" --description="Aid coordination images"
}

step_build() {
  # Build context is the parent (components/) so whatsapp/api is included.
  g builds submit --region="$REGION" --tag "$IMAGE" -f Dockerfile ..
}

step_grant() {
  # The runtime SA needs read access to the shared secrets (it already has
  # cloudsql.client from the webhook deploy).
  local pair
  for pair in "${SECRET_MAP[@]}"; do
    g secrets add-iam-policy-binding "${pair%%:*}" \
      --member="serviceAccount:$RUN_SA" \
      --role="roles/secretmanager.secretAccessor" >/dev/null || true
  done
}

step_service() {
  # Public (the frontend calls it from browsers); auth is the JWT bearer token.
  # Credentialed CORS is restricted to WEB_ORIGINS.
  g run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" \
    --service-account="$RUN_SA" \
    --allow-unauthenticated --port=8080 \
    --min-instances=0 --max-instances=3 --cpu=1 --memory=512Mi \
    --set-cloudsql-instances="$(sql_conn)" \
    --set-env-vars="^@^APP_ENV=production@WEB_ORIGINS=$WEB_ORIGINS@OPENAI_MODEL=$OPENAI_MODEL" \
    "$(secret_flags)"
}

step_url() {
  local url
  url="$(g run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
  echo "Dashboard API URL: $url"
  echo "OpenAPI:           $url/openapi.json"
  echo "Health:            $url/health"
}

step_deploy() {
  if [[ -n "$(git status --porcelain -- . 2>/dev/null)" ]]; then
    echo "Uncommitted changes; commit or stash first (image is tagged by commit)." >&2
    exit 1
  fi
  for s in build grant service url; do echo "== $s"; "step_$s"; done
}

main() {
  local s="${1:-}"
  case "$s" in
    deploy) step_deploy ;;
    all) for s in registry build grant service url; do echo "== $s"; "step_$s"; done ;;
    registry|build|grant|service|url) "step_$s" ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
  esac
}

main "$@"
