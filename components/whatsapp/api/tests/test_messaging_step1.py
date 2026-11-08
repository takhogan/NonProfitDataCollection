"""Step 1 WhatsApp send pipeline tests, using the fake adapter (no network).

Covers: inbound text -> greeting queued; sender sends and stores wamid; delivery
status updates the row; replayed inbound event is idempotent (no second reply).
"""
import pytest

from app.models.outbox import OutboundMessage
from app.models.system import InboundEvent
from app.whatsapp.adapter import FakeAdapter, SendError
from app.whatsapp.messaging import (
    GREETING_ES,
    process_inbound_event,
    send_outbox_batch,
)


def _message_event(db, provider_message_id="wamid.IN1", from_="584121112233"):
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "PN-1"},
            "messages": [{"id": provider_message_id, "from": from_,
                          "type": "text", "text": {"body": "hola"}}],
        }}]}]
    }
    ev = InboundEvent(event_type="message", channel_account_id="PN-1",
                      provider_message_id=provider_message_id, payload_json=payload)
    db.add(ev)
    db.flush()
    return ev


def _status_event(db, status_id, status, provider_message_id="wamid.ST1"):
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "PN-1"},
            "statuses": [{"id": status_id, "status": status, "timestamp": "123"}],
        }}]}]
    }
    ev = InboundEvent(event_type="status", channel_account_id="PN-1",
                      provider_message_id=provider_message_id, payload_json=payload)
    db.add(ev)
    db.flush()
    return ev


def test_inbound_text_queues_greeting_and_marks_processed(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev, org_name="Agua Azul")
    db_session.commit()

    assert ev.processed_at is not None
    rows = db_session.query(OutboundMessage).all()
    assert len(rows) == 1
    assert rows[0].status == "queued"
    assert rows[0].recipient == "584121112233"
    assert rows[0].phone_number_id == "PN-1"
    assert rows[0].body == GREETING_ES.format(org="Agua Azul")


def test_sender_sends_and_stores_wamid(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev)
    db_session.commit()

    adapter = FakeAdapter()
    attempted = send_outbox_batch(db_session, adapter, batch_size=10)
    assert attempted == 1
    assert len(adapter.sent) == 1

    row = db_session.query(OutboundMessage).one()
    assert row.status == "sent"
    assert row.provider_message_id == "wamid.FAKE1"
    assert row.sent_at is not None


def test_status_delivered_then_read_updates_row(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev)
    db_session.commit()
    send_outbox_batch(db_session, FakeAdapter(), batch_size=10)
    row = db_session.query(OutboundMessage).one()
    wamid = row.provider_message_id

    process_inbound_event(db_session, _status_event(db_session, wamid, "delivered",
                                                    provider_message_id="wamid.ST-d"))
    db_session.commit()
    db_session.refresh(row)
    assert row.status == "delivered"
    assert row.delivered_at is not None

    process_inbound_event(db_session, _status_event(db_session, wamid, "read",
                                                    provider_message_id="wamid.ST-r"))
    db_session.commit()
    db_session.refresh(row)
    assert row.status == "read"
    assert row.read_at is not None


def test_status_does_not_regress(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev)
    db_session.commit()
    send_outbox_batch(db_session, FakeAdapter(), batch_size=10)
    row = db_session.query(OutboundMessage).one()
    wamid = row.provider_message_id

    # read first, then a late "delivered" must not move the status backwards.
    process_inbound_event(db_session, _status_event(db_session, wamid, "read",
                                                    provider_message_id="wamid.ST-r"))
    db_session.commit()
    process_inbound_event(db_session, _status_event(db_session, wamid, "delivered",
                                                    provider_message_id="wamid.ST-d"))
    db_session.commit()
    db_session.refresh(row)
    assert row.status == "read"


def test_replayed_inbound_event_is_idempotent(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev, org_name="Agua Azul")
    db_session.commit()
    # Simulate the SAME event object being processed again (dedupe_key guards it).
    process_inbound_event(db_session, ev, org_name="Agua Azul")
    db_session.commit()
    assert db_session.query(OutboundMessage).count() == 1


def test_retryable_failure_then_success(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev)
    db_session.commit()

    adapter = FakeAdapter(fail_times=1)  # first attempt fails, second succeeds
    send_outbox_batch(db_session, adapter, batch_size=10)
    row = db_session.query(OutboundMessage).one()
    assert row.status == "queued"  # still queued after the transient failure
    assert row.attempts == 1

    send_outbox_batch(db_session, adapter, batch_size=10)
    db_session.refresh(row)
    assert row.status == "sent"
    assert row.attempts == 2


def test_fatal_failure_marks_failed(db_session):
    ev = _message_event(db_session)
    process_inbound_event(db_session, ev)
    db_session.commit()

    send_outbox_batch(db_session, FakeAdapter(fatal=True), batch_size=10)
    row = db_session.query(OutboundMessage).one()
    assert row.status == "failed"
    assert row.failed_at is not None
    assert row.last_error
