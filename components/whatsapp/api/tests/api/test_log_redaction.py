"""API-112: logs never contain phone numbers, names, message text, emails or tokens.

Drives the main request paths with seeded personal data through the
production log handler (redaction filter + JSON formatter) and scans the
output for every seeded value.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import config
from app.auth.logs import build_handler, redact
from tests.api.conftest import PASSWORDS, sign_in

NAME = "Carmen Rodríguez"
PHONE_DISPLAY = "+58 412-555-0199"
PHONE_WA = "584125550199"
MESSAGE = "sin agua desde el lunes en la casa azul"
EMAIL = "a@example.org"
VERIFY_TOKEN = "dev-verify-token"

SEEDED = [NAME, "Rodríguez", PHONE_DISPLAY, PHONE_WA, "555-0199", "5550199", MESSAGE,
          EMAIL, PASSWORDS[EMAIL], VERIFY_TOKEN]


@pytest.fixture()
def log_output():
    buf = io.StringIO()
    handler = build_handler(buf, json_logs=True)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield buf
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()


def test_no_personal_data_in_logs(client, staff, auth_store, clock, monkeypatch, log_output):
    monkeypatch.setattr(config.get_settings(), "app_secret", "test-secret")

    # Sign-in failures and success with the seeded email/password.
    client.post("/v1/auth/password/login", json={"email": EMAIL, "password": "wrong-password"})
    client.post("/v1/auth/password/login", json={"email": "ghost@x.org", "password": "x" * 12})
    csrf = {"X-CSRF-Token": sign_in(client, auth_store, clock, EMAIL)}

    # Assisted intake with a named contact; a validation error carrying a phone.
    intake = {"reference_code": "LOG-1",
              "contacts": [{"preferred_name": NAME}],
              "answers": {"notes": MESSAGE, "phone": PHONE_DISPLAY},
              "needs": [{"category": "water_delivery", "requested_quantity": 5,
                         "unit": "liters"}]}
    assert client.post("/v1/households", json=intake, headers=csrf).status_code == 201
    client.post("/v1/households", json={**intake, "estimated_member_count": PHONE_DISPLAY},
                headers=csrf)
    client.get(f"/v1/households/{PHONE_WA}")  # personal data in a path segment

    # WhatsApp: handshake (verify token in query), signed and unsigned messages.
    client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe",
                                             "hub.verify_token": VERIFY_TOKEN,
                                             "hub.challenge": "1"})
    payload = {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PN-1"},
        "contacts": [{"profile": {"name": NAME}, "wa_id": PHONE_WA}],
        "messages": [{"id": "wamid.LOG", "from": PHONE_WA, "text": {"body": MESSAGE}}],
    }}]}]}
    raw = json.dumps(payload).encode()
    assert client.post("/webhooks/whatsapp", content=raw,
                       headers={"X-Hub-Signature-256": _sign(raw)}).status_code == 200
    client.post("/webhooks/whatsapp", content=raw,
                headers={"X-Hub-Signature-256": "sha256=bad"})

    # An unhandled exception whose message contains personal data.
    boom = APIRouter()

    @boom.get("/boom-log")
    def _boom():
        raise RuntimeError(f"{NAME} {PHONE_DISPLAY} {MESSAGE}")

    from app.main import create_app
    app = create_app()
    app.include_router(boom)
    TestClient(app, raise_server_exceptions=False).get("/boom-log")

    # A careless log call: the redaction filter is the safety net.
    logging.getLogger("app.careless").info(
        "contact %s at %s", EMAIL, PHONE_DISPLAY, extra={"payload": MESSAGE})

    out = log_output.getvalue()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) > 10, "expected access and auth log lines"
    for ln in lines:
        json.loads(ln)  # every line is structured JSON
    for value in SEEDED:
        assert value not in out, f"leaked into logs: {value!r}"
    assert '"route": "/v1/households/{household_id}"' in out  # templates, not raw paths
    assert "unhandled_exception" in out and "RuntimeError" in out


@pytest.mark.parametrize("raw,leak", [
    ("call +58 412 555 0199 now", "555"),
    ("wa 584125550199", "584125550199"),
    ("mail carmen.r@example.org", "carmen"),
    ("Authorization: Bearer eyJhbGciOi.abc.def", "eyJhbGciOi"),
    ("url?token=abcdef123", "abcdef123"),
])
def test_redact_masks_patterns(raw, leak):
    assert leak not in redact(raw)


def test_redact_keeps_uuids():
    uid = "1eb5e1be-9f8b-4c2a-8d3e-1234567890ab"
    assert redact(f"user {uid}") == f"user {uid}"
