"""Background worker: poll the durable inbound_event inbox and process events.

Deployed as a second Cloud Run service from the SAME image as the API, with a
different command (python -m scripts.worker). It shares the same database and
domain code; it does not open an HTTP port.

Each cycle does two things:
  1. process inbound_event rows: for a text message, queue a canned Spanish
     greeting into the outbox in the SAME transaction as marking the event
     processed; for a status event, update the matching outbox row.
  2. send queued outbox rows via the WhatsApp adapter, storing the provider
     message id and retrying transient failures.

The loop is idempotent: an event already marked processed is skipped, and a
per-event dedupe_key prevents a replayed event from queueing a second reply, so
a worker restart does not double-handle anything or double-send.
"""
from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models.system import InboundEvent
from app.whatsapp.adapter import get_adapter
from app.whatsapp.messaging import process_inbound_event, send_outbox_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

_running = True


def _stop(signum, _frame):
    global _running
    log.info("received signal %s, shutting down after current batch", signum)
    _running = False


def process_batch(db: Session, batch_size: int) -> int:
    """Claim and process one batch of unprocessed inbound events. Returns count."""
    events = list(
        db.scalars(
            select(InboundEvent)
            .where(InboundEvent.processed_at.is_(None))
            .order_by(InboundEvent.received_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)  # ignored by SQLite, honored by Postgres
        )
    )
    for event in events:
        log.info(
            "processing inbound_event id=%s type=%s provider_message_id=%s signature_valid=%s",
            event.id, event.event_type, event.provider_message_id, event.signature_valid,
        )
        # Queue any reply AND mark processed in the same transaction (outbox).
        process_inbound_event(db, event, org_name=get_settings().pilot_org_name)
    if events:
        db.commit()
    return len(events)


def run() -> None:
    settings = get_settings()
    settings.validate_runtime()  # fail fast on bad production config, same as the API

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    interval = settings.worker_poll_interval_seconds
    batch_size = settings.worker_batch_size
    log.info(
        "worker started (env=%s, poll=%ss, batch=%s)",
        settings.app_env, interval, batch_size,
    )

    adapter = get_adapter()

    while _running:
        db = SessionLocal()
        try:
            handled = process_batch(db, batch_size)
            sent = send_outbox_batch(db, adapter, batch_size)
        except Exception:  # keep the worker alive on transient errors
            log.exception("error while processing batch")
            db.rollback()
            handled, sent = 0, 0
        finally:
            db.close()

        if handled == 0 and sent == 0:
            # Idle: sleep in short slices so SIGTERM is handled promptly.
            slept = 0.0
            while _running and slept < interval:
                time.sleep(min(0.5, interval - slept))
                slept += 0.5

    log.info("worker stopped")


if __name__ == "__main__":
    run()
