"""Background worker: poll the durable inbound_event inbox and process events.

Deployed as a second Cloud Run service from the SAME image as the API, with a
different command (python -m scripts.worker). It shares the same database and
domain code. Cloud Run services must accept connections on $PORT or the
startup probe kills the instance, so when PORT is set (only on Cloud Run) the
worker also answers GET /health on that port from a background thread. It
serves nothing else. Locally PORT is unset and no port is opened.

Each cycle (see app/whatsapp/):
  1. surge mode: if the oldest waiting message is older than SURGE_LAG_SECONDS,
     queue one holding reply per waiting conversation (OPW-035);
  2. process inbound_event rows: route each message to its organization's
     conversation engine (questionnaire state machine) and each delivery status
     to the matching outbox/message row (inbound.py, engine.py);
  3. send due outbox_message rows through the adapter with the 24-hour window,
     opt-out gate, templates, rate limit and uncertain-send reconciliation
     (sender.py).

Everything is idempotent: inbound messages are unique per provider id, replies
are queued in the same transaction as the state change, and a send that may
have reached Meta is never resent.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


from app.config import get_settings
from app.crypto import ensure_ready
from app.models.base import utcnow
from app.whatsapp.adapter import get_adapter
from app.whatsapp.extraction import get_extractor
from app.whatsapp.inbound import pending_event_ids, process_event, queue_surge_holding
from app.whatsapp.sender import send_pending

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

_running = True


def _stop(signum, _frame):
    global _running
    log.info("received signal %s, shutting down after current batch", signum)
    _running = False


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server naming)
        ok = self.path in ("/", "/health")
        body = b'{"status":"ok"}' if ok else b'{"status":"not_found"}'
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # keep probe hits out of the logs
        pass


def start_health_server(port: int) -> ThreadingHTTPServer:
    """Serve GET /health on `port` in a daemon thread (for the Cloud Run probe)."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()
    log.info("health endpoint listening on :%s", port)
    return server


def run_cycle(adapter, extractor, batch_size: int, session_factory=None) -> tuple[int, int]:
    """One worker cycle: surge holding replies, inbound events, then sends."""
    now = utcnow()
    queue_surge_holding(batch_size, now, session_factory)
    handled = 0
    for event_id in pending_event_ids(batch_size, now, session_factory):
        status = process_event(event_id, extractor, now, session_factory)
        log.info("inbound_event id=%s -> %s", event_id, status)
        handled += 1
    sent = send_pending(adapter, batch_size, utcnow(), session_factory)
    return handled, sent


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

    port = os.environ.get("PORT")
    health = start_health_server(int(port)) if port else None

    # Unwrap the field-encryption root key now: a KMS or permission problem
    # should stop the worker at startup, not halfway through a conversation.
    ensure_ready()

    adapter = get_adapter()

    extractor = get_extractor()
    log.info("openai extraction: %s", "on" if extractor else "off")

    while _running:
        try:
            handled, sent = run_cycle(adapter, extractor, batch_size)
        except Exception:  # keep the worker alive on transient errors
            log.exception("error while processing batch")
            handled, sent = 0, 0

        if handled == 0 and sent == 0:
            # Idle: sleep in short slices so SIGTERM is handled promptly.
            slept = 0.0
            while _running and slept < interval:
                time.sleep(min(0.5, interval - slept))
                slept += 0.5

    if health is not None:
        health.shutdown()
    log.info("worker stopped")


if __name__ == "__main__":
    run()
