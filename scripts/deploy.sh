#!/usr/bin/env bash
# Deploy the deployable components to the LIVE GCP project (Cloud Run, Cloud SQL,
# Firebase Hosting). The webhook serves a real WhatsApp number.
#
#   scripts/deploy.sh [all|api|dashboard|web ...] [--dry-run] [--yes]
#   npm run deploy -- --dry-run           # print the plan and commands, run nothing
#   npm run deploy:api                    # one target
#
# Targets run in this order, whatever order you give them:
#   api        components/whatsapp/api -> ./deploy/gcloud-deploy.sh deploy
#              (Cloud Build image, then the `aid-migrate` Cloud Run job runs
#              `alembic upgrade head` (--wait), then the whatsapp-webhook service,
#              then the aid-worker service (inbox poller + reply sender,
#              min-instances=1). See DEPLOY.md section 8.
#   dashboard  components/api: image built with components/cloudbuild.dashboard.yaml,
#              then components/api/deploy/gcloud-deploy.sh grant + service + url
#              with the same IMAGE_TAG. It shares the api's database, so it goes
#              after the api's migrations. (That script's own `build` step passes
#              `-f` to `gcloud builds submit`, which has no such flag.)
#   web        components/web -> firebase deploy --only hosting (static-site/ only;
#              the React build is not hosted yet, see components/web/HOSTING.md).
#
# Nothing is skipped automatically: every target you name is deployed. The
# preflight prints the deployed image tag of each Cloud Run service and how many
# files changed since that commit, so you can decide what to name.
#
# Without --yes it asks you to type "deploy". Without a terminal it refuses
# unless --yes is given. Agents: never run this without the user's explicit
# approval in chat (see CLAUDE.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ID="${PROJECT_ID:-csl-metron-webhook}"
REGION="${REGION:-us-east4}"
API_SERVICE="${API_SERVICE:-whatsapp-webhook}"
DASH_SERVICE="${DASH_SERVICE:-dashboard-api}"

DRY_RUN=0
YES=0
TARGETS=()
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY_RUN=1 ;;
    --yes|-y) YES=1 ;;
    all) TARGETS+=(api dashboard web) ;;
    api|dashboard|web) TARGETS+=("$a") ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) echo "unknown argument: $a (targets: all api dashboard web; flags: --dry-run --yes)" >&2; exit 2 ;;
  esac
done
[[ ${#TARGETS[@]} -gt 0 ]] || { sed -n '2,29p' "$0"; exit 2; }

has() { local t; for t in "${TARGETS[@]}"; do [[ "$t" == "$1" ]] && return 0; done; return 1; }
ORDERED=()
for t in api dashboard web; do has "$t" && ORDERED+=("$t"); done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
PROBLEMS=0
fail() {
  printf '\033[31merror:\033[0m %s\n' "$*" >&2
  PROBLEMS=$((PROBLEMS + 1))
}

# Run a command, or only print it with --dry-run. $1 is the directory.
run_in() {
  local dir="$1"; shift
  local shown="${dir#"$ROOT"}"; shown="${shown#/}"
  printf '\033[2m+ (cd %s && %s)\033[0m\n' "${shown:-.}" "$*"
  [[ $DRY_RUN -eq 1 ]] && return 0
  (cd "$dir" && "$@")
}

# ------------------------------------------------------------------ preflight
bold "Preflight (project $PROJECT_ID, region $REGION; targets: ${ORDERED[*]})"
GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD)"
echo "HEAD: $GIT_SHA on $(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"

# Images are tagged with the commit hash, so the tree must match HEAD. The
# dashboard image bundles whatsapp/api as well, so check all of components/.
if [[ -n "$(git -C "$ROOT" status --porcelain -- components/)" ]]; then
  fail "uncommitted changes under components/; commit them first (images are tagged by commit)"
fi

if has api || has dashboard; then
  if ! command -v gcloud >/dev/null; then
    fail "gcloud not on PATH (install the Google Cloud SDK)"
  else
    ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
    if [[ -z "$ACCOUNT" ]]; then
      fail "no active gcloud account; run: gcloud auth login"
    else
      echo "gcloud account: $ACCOUNT"
      if ! gcloud projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null 2>&1; then
        fail "cannot read project $PROJECT_ID with $ACCOUNT (wrong account, or token expired: gcloud auth login)"
      fi
      # Informational only: what is live, and what changed since.
      for pair in "api:$API_SERVICE:components/whatsapp/api" "dashboard:$DASH_SERVICE:components/api components/whatsapp/api"; do
        IFS=: read -r t svc paths <<<"$pair"
        has "$t" || continue
        img="$(gcloud run services describe "$svc" --project="$PROJECT_ID" --region="$REGION" \
          --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)"
        if [[ -z "$img" ]]; then
          echo "$svc: not deployed yet"
          continue
        fi
        tag="${img##*:}"
        # shellcheck disable=SC2086
        if git -C "$ROOT" cat-file -e "$tag^{commit}" 2>/dev/null; then
          n="$(git -C "$ROOT" diff --name-only "$tag" HEAD -- $paths | wc -l | tr -d ' ')"
          echo "$svc: live image tag $tag; $n file(s) changed since under ${paths}"
        else
          echo "$svc: live image tag $tag (not a commit in this checkout; cannot compare)"
        fi
      done
    fi
  fi
fi

if has web; then
  if ! command -v firebase >/dev/null; then
    fail "firebase CLI not on PATH (npm i -g firebase-tools); see components/web/HOSTING.md for the REST fallback"
  else
    echo "firebase CLI: $(firebase --version 2>/dev/null)"
  fi
  # Everything in static-site/ is published: allow only the expected page types.
  unexpected="$(cd "$ROOT/components/web/static-site" && find . -type f ! -name '*.html' ! -name '*.css' ! -name '.*' ! -name '*.log')"
  if [[ -n "$unexpected" ]]; then
    fail "components/web/static-site has files other than .html/.css (all of it is published):"$'\n'"$unexpected"
  else
    echo "static-site: $(cd "$ROOT/components/web/static-site" && find . -type f ! -name '.*' ! -name '*.log' | sort | tr '\n' ' ')"
  fi
fi

if [[ $PROBLEMS -gt 0 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    warn "$PROBLEMS preflight problem(s); a real deploy would stop here"
  else
    exit 1
  fi
fi

# ------------------------------------------------------------------ confirm
bold "Plan"
for t in "${ORDERED[@]}"; do
  case "$t" in
    api) echo "  api        build aid-api:$GIT_SHA, run migrations (aid-migrate job), deploy $API_SERVICE and aid-worker" ;;
    dashboard) echo "  dashboard  build dashboard-api:$GIT_SHA, deploy $DASH_SERVICE" ;;
    web) echo "  web        firebase deploy --only hosting (metron-reporter.web.app)" ;;
  esac
done

if [[ $DRY_RUN -eq 0 && $YES -eq 0 ]]; then
  if [[ ! -t 0 ]]; then
    echo "Refusing to deploy without a terminal; pass --yes to confirm." >&2
    exit 1
  fi
  read -r -p "This deploys to the LIVE project $PROJECT_ID. Type 'deploy' to continue: " answer
  [[ "$answer" == "deploy" ]] || { echo "Aborted."; exit 1; }
fi
[[ $DRY_RUN -eq 1 ]] && bold "Dry run: commands are printed, not run"

# ------------------------------------------------------------------ deploy
for t in "${ORDERED[@]}"; do
  bold "== $t"
  case "$t" in
    api)
      run_in "$ROOT/components/whatsapp/api" env PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
        ./deploy/gcloud-deploy.sh deploy
      ;;
    dashboard)
      run_in "$ROOT" gcloud builds submit --project="$PROJECT_ID" --region="$REGION" \
        --config=components/cloudbuild.dashboard.yaml --substitutions=_TAG="$GIT_SHA" components/
      for step in grant service url; do
        run_in "$ROOT/components/api" env PROJECT_ID="$PROJECT_ID" REGION="$REGION" IMAGE_TAG="$GIT_SHA" \
          ./deploy/gcloud-deploy.sh "$step"
      done
      ;;
    web)
      run_in "$ROOT/components/web" firebase deploy --only hosting --project "$PROJECT_ID"
      ;;
  esac
done
if [[ $DRY_RUN -eq 1 ]]; then bold "Dry run done; nothing was deployed."; else bold "Done."; fi
