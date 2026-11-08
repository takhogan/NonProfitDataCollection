"""WhatsApp inbound webhooks.

GET  /webhooks/whatsapp  -> Meta verification handshake (echo hub.challenge).
POST /webhooks/whatsapp  -> verify X-Hub-Signature-256, persist the raw event to
                           inbound_event, return 200 immediately. A missing or
                           invalid signature gets 401 and nothing is stored; if
                           APP_SECRET is not configured, POSTs get 503 rather
                           than accepting unverifiable data.

No LLM calls and no outbound sends happen here; a separate worker polls
unprocessed inbound_event rows. Both WhatsApp message and delivery-status
payloads arrive at this one URL and are routed by payload shape.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.ratelimit import limit_webhook
from app.config import get_settings
from app.db import get_db
from app.models.system import InboundEvent

# Per-IP rate limit (API-111) runs before any signature work.
router = APIRouter(prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(limit_webhook)])


@router.get("/whatsapp")
def verify_subscription(
    hub_mode: str | None = None,
    hub_verify_token: str | None = None,
    hub_challenge: str | None = None,
    request: Request = None,
):
    """Meta sends hub.mode, hub.verify_token, hub.challenge as query params.

    FastAPI cannot bind dotted names, so read them from the raw query string.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    settings = get_settings()
    if mode == "subscribe" and token and token == settings.verify_token:
        return PlainTextResponse(challenge or "")
    return Response(status_code=403)


def _verify_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    if not app_secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def _route_payload(payload: dict) -> tuple[str, str | None, str | None]:
    """Return (event_type, channel_account_id, provider_message_id).

    Routes by payload shape: WhatsApp nests under
    entry[].changes[].value.{messages|statuses}.
    """
    event_type = "unknown"
    channel_account_id = None
    provider_message_id = None
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        channel_account_id = value.get("metadata", {}).get("phone_number_id")
        if value.get("messages"):
            event_type = "message"
            provider_message_id = value["messages"][0].get("id")
        elif value.get("statuses"):
            event_type = "status"
            provider_message_id = value["statuses"][0].get("id")
    except (KeyError, IndexError, TypeError):
        pass
    return event_type, channel_account_id, provider_message_id


@router.post("/whatsapp")
async def receive_event(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Response:
    raw = await request.body()
    settings = get_settings()
    if not settings.app_secret:
        # Misconfigured deployment: never accept unverifiable provider data.
        # A 5xx makes Meta retry later instead of the event being lost.
        return Response(status_code=503)
    if not _verify_signature(settings.app_secret, raw, x_hub_signature_256):
        # Unauthenticated caller: do not persist attacker-controlled payloads.
        return Response(status_code=401)
    signature_ok = True

    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = {"_raw": raw.decode("utf-8", "replace")}

    event_type, channel_account_id, provider_message_id = _route_payload(payload)

    event = InboundEvent(
        event_type=event_type,
        channel_account_id=channel_account_id,
        provider_message_id=provider_message_id,
        payload_json=payload,
        signature_valid=signature_ok,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Replayed provider message (same channel account + message id): already
        # stored. Acknowledge idempotently; the worker will not double-process.
        db.rollback()

    # Always 200 fast: durable acceptance happened above; processing is async.
    return Response(status_code=200)
