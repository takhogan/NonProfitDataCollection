import hashlib
import hmac
import json

from app.config import get_settings
from app.models.system import InboundEvent

MESSAGE_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "metadata": {"phone_number_id": "PN-1"},
                        "messages": [{"id": "wamid.ABC", "text": {"body": "hola"}}],
                    }
                }
            ]
        }
    ]
}

STATUS_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "metadata": {"phone_number_id": "PN-1"},
                        "statuses": [{"id": "wamid.ABC", "status": "delivered"}],
                    }
                }
            ]
        }
    ]
}


def _sign(body: bytes) -> str:
    secret = get_settings().app_secret.encode()
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_verification_handshake_echoes_challenge(client):
    token = get_settings().verify_token
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "42"},
    )
    assert resp.status_code == 200
    assert resp.text == "42"


def test_verification_handshake_rejects_bad_token(client):
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"},
    )
    assert resp.status_code == 403


def test_post_persists_message_event(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_secret", "test-secret")
    raw = json.dumps(MESSAGE_PAYLOAD).encode()
    resp = client.post(
        "/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": _sign(raw)}
    )
    assert resp.status_code == 200

    events = db_session.query(InboundEvent).all()
    assert len(events) == 1
    assert events[0].event_type == "message"
    assert events[0].provider_message_id == "wamid.ABC"
    assert events[0].signature_valid is True
    assert events[0].processed_at is None  # worker handles this later


def test_post_routes_status_event(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_secret", "test-secret")
    raw = json.dumps(STATUS_PAYLOAD).encode()
    resp = client.post(
        "/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": _sign(raw)}
    )
    assert resp.status_code == 200
    ev = db_session.query(InboundEvent).one()
    assert ev.event_type == "status"


def test_bad_signature_still_200_but_flagged(client, db_session, monkeypatch):
    # We persist even unverified events (quarantine), flagged signature_valid=False,
    # and always ack 200 so the provider does not hammer retries.
    monkeypatch.setattr(get_settings(), "app_secret", "test-secret")
    raw = json.dumps(MESSAGE_PAYLOAD).encode()
    resp = client.post(
        "/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=deadbeef"}
    )
    assert resp.status_code == 200
    ev = db_session.query(InboundEvent).one()
    assert ev.signature_valid is False


def test_duplicate_provider_message_deduped(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_secret", "test-secret")
    raw = json.dumps(MESSAGE_PAYLOAD).encode()
    headers = {"X-Hub-Signature-256": _sign(raw)}
    assert client.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
    # Replay the exact same provider message id: still 200, no second row.
    assert client.post("/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
    assert db_session.query(InboundEvent).count() == 1
