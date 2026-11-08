"""DEPRECATED Step 1 (canned greeting over ``outbound_message``). The worker no
longer calls this module; the conversation engine (engine.py, inbound.py,
sender.py) replaced it. Kept so its tests document the old behavior until the
``outbound_message`` table is dropped.

Inbound processing + outbox sending for WhatsApp (Step 1: canned greeting).

process_inbound_event: route one inbound_event. For a text message, queue a
single Spanish greeting into the outbox IN THE SAME TRANSACTION as marking the
event processed. For a status event, update the matching outbox row. The caller
commits.

send_outbox_batch: claim queued outbox rows, send them via the adapter, store the
provider message id, and retry transient failures up to max_attempts.

Step 1 keeps zero conversation state and no org resolution — that is Step 2.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.outbox import OutboundMessage
from app.models.system import InboundEvent
from app.whatsapp.adapter import SendError, WhatsAppAdapter

log = logging.getLogger("whatsapp.messaging")

# Plan's suggested first bot line (PLATFORM_PLAN.md "Suggested first bot
# conversation"), with the NGO placeholder filled for the pilot. Step 2 replaces
# this canned reply with the AI intake conversation.
GREETING_ES = (
    "Somos {org}. Recogemos información sobre cortes de luz y agua para "
    "coordinar apoyo. Esto no garantiza ayuda. Puedes pedir hablar con una "
    "persona."
)
DEFAULT_ORG_NAME = "la ONG"


def _extract_message(payload: dict) -> dict | None:
    """Return {from, text, phone_number_id} for a text message, else None."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        phone_number_id = value.get("metadata", {}).get("phone_number_id")
        msg = value["messages"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if msg.get("type") != "text":
        return None
    return {
        "from": msg.get("from"),
        "text": msg.get("text", {}).get("body", ""),
        "phone_number_id": phone_number_id,
    }


def _extract_statuses(payload: dict) -> list[dict]:
    """Return a list of {id, status, timestamp} for delivery-status events."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        statuses = value.get("statuses") or []
    except (KeyError, IndexError, TypeError):
        return []
    return [
        {"id": s.get("id"), "status": s.get("status"), "timestamp": s.get("timestamp")}
        for s in statuses
    ]


_STATUS_FIELD = {
    "sent": "sent_at",
    "delivered": "delivered_at",
    "read": "read_at",
    "failed": "failed_at",
}


def _apply_status(db: Session, status_id: str, status: str) -> None:
    """Update the outbox row whose provider_message_id matches a status event.

    Never regress a terminal/advanced state on a late or out-of-order event.
    """
    row = db.scalar(
        select(OutboundMessage).where(OutboundMessage.provider_message_id == status_id)
    )
    if row is None:
        return  # status for a message we did not send (or not yet persisted)
    field = _STATUS_FIELD.get(status)
    if field and getattr(row, field) is None:
        setattr(row, field, utcnow())
    # Advance status forward only: sent < delivered < read; failed is terminal.
    order = {"sent": 1, "delivered": 2, "read": 3}
    if status == "failed":
        row.status = "failed"
    elif status in order and order.get(status, 0) > order.get(row.status, 0):
        row.status = status


def process_inbound_event(db: Session, event: InboundEvent, *, org_name: str = DEFAULT_ORG_NAME) -> None:
    """Handle one inbound event. Caller commits. Idempotent per event via dedupe_key."""
    if event.event_type == "message":
        msg = _extract_message(event.payload_json)
        if msg and msg["from"] and msg["phone_number_id"]:
            dedupe_key = f"greeting:{event.id}"
            exists = db.scalar(
                select(OutboundMessage).where(OutboundMessage.dedupe_key == dedupe_key)
            )
            if exists is None:
                db.add(
                    OutboundMessage(
                        phone_number_id=msg["phone_number_id"],
                        recipient=msg["from"],
                        message_type="text",
                        body=GREETING_ES.format(org=org_name),
                        status="queued",
                        dedupe_key=dedupe_key,
                    )
                )
    elif event.event_type == "status":
        for st in _extract_statuses(event.payload_json):
            if st["id"] and st["status"]:
                _apply_status(db, st["id"], st["status"])

    event.processed_at = utcnow()


def send_outbox_batch(db: Session, adapter: WhatsAppAdapter, batch_size: int) -> int:
    """Send queued outbox rows. Returns count attempted. Caller need not commit;
    this commits per-row so a crash mid-batch does not lose progress."""
    rows = list(
        db.scalars(
            select(OutboundMessage)
            .where(OutboundMessage.status == "queued")
            .where(OutboundMessage.attempts < OutboundMessage.max_attempts)
            .order_by(OutboundMessage.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        row.attempts += 1
        try:
            result = adapter.send_text(
                phone_number_id=row.phone_number_id, to=row.recipient, body=row.body
            )
        except SendError as exc:
            row.last_error = str(exc)[:1000]
            if exc.retryable and row.attempts < row.max_attempts:
                row.status = "queued"  # leave queued for another attempt
                log.warning("send retryable failure (attempt %s): %s", row.attempts, exc)
            else:
                row.status = "failed"
                row.failed_at = utcnow()
                log.error("send permanently failed: %s", exc)
        else:
            row.provider_message_id = result.provider_message_id
            row.status = "sent"
            row.sent_at = utcnow()
            row.last_error = None
            log.info("sent outbound id=%s wamid=%s", row.id, result.provider_message_id)
        db.commit()
    return len(rows)
