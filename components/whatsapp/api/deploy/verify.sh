#!/usr/bin/env bash
# Smoke-test the deployed webhook with SYNTHETIC data only.
#
#   deploy/verify.sh
#
# Checks: /health; GET handshake with right/wrong verify token; POST with a bad
# signature -> 401; a correctly signed synthetic payload -> 200 and a row in
# inbound_event (confirmed by a one-off execution of the migrate job's image).
# Secrets are read into shell variables from Secret Manager and never printed.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-csl-metron-webhook}"
REGION="${REGION:-us-east4}"
SERVICE="${SERVICE:-whatsapp-webhook}"
g() { gcloud --project="$PROJECT_ID" --quiet "$@"; }

URL="$(g run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
VERIFY_TOKEN="$(g secrets versions access latest --secret=verify-token)"
APP_SECRET="$(g secrets versions access latest --secret=whatsapp-app-secret)"
fail=0
check() { # name expected actual
  if [[ "$2" == "$3" ]]; then echo "PASS $1 ($3)"; else echo "FAIL $1: expected $2, got $3"; fail=1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check "GET /health" 200 "$(code "$URL/health")"

challenge="synthetic-$RANDOM"
body="$(curl -s "$URL/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=$VERIFY_TOKEN&hub.challenge=$challenge")"
check "handshake echoes challenge" "$challenge" "$body"
check "handshake wrong token" 403 \
  "$(code "$URL/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1")"

msg_id="wamid.SYNTHETIC-$(date +%s)-$RANDOM"
payload="{\"object\":\"whatsapp_business_account\",\"entry\":[{\"changes\":[{\"field\":\"messages\",\"value\":{\"metadata\":{\"phone_number_id\":\"SYNTHETIC-TEST\"},\"messages\":[{\"id\":\"$msg_id\",\"type\":\"text\",\"text\":{\"body\":\"synthetic smoke test\"}}]}}]}]}"
sig="sha256=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$APP_SECRET" -r | cut -d' ' -f1)"

check "POST bad signature" 401 "$(code -X POST "$URL/webhooks/whatsapp" \
  -H 'content-type: application/json' -H 'X-Hub-Signature-256: sha256=00' --data-binary "$payload")"
check "POST no signature" 401 "$(code -X POST "$URL/webhooks/whatsapp" \
  -H 'content-type: application/json' --data-binary "$payload")"
check "POST signed synthetic payload" 200 "$(code -X POST "$URL/webhooks/whatsapp" \
  -H 'content-type: application/json' -H "X-Hub-Signature-256: $sig" --data-binary "$payload")"

# Confirm persistence: run the app image once with a read-only query.
query="from app.db import SessionLocal; from app.models.system import InboundEvent as E; \
s=SessionLocal(); n=s.query(E).filter(E.provider_message_id=='$msg_id', E.signature_valid.is_(True)).count(); \
print('VERIFY_PERSISTED', n); raise SystemExit(0 if n==1 else 1)"
if g run jobs execute aid-migrate --region="$REGION" --wait \
     --args="^|^-c|$query" >/dev/null 2>&1; then
  echo "PASS signed event persisted in inbound_event ($msg_id)"
else
  echo "FAIL signed event not found in inbound_event ($msg_id)"; fail=1
fi
exit "$fail"
