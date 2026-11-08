"""WhatsApp conversation-engine fixtures: migrated + seeded PostgreSQL (RLS on).

Tests drive the real pipeline: a webhook-shaped payload is stored in
``inbound_event`` (as the webhook route would), then one worker cycle runs
(``scripts.worker.run_cycle``) with the FakeAdapter and an optional
FakeExtractor. Skipped when no PostgreSQL server is reachable.
"""
from __future__ import annotations

import itertools
import time

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from tests.database._pg import _SERVER, alembic_config, scratch_database

PNID_PROT = "PNID-PROTECTIVE"
PNID_STD = "PNID-STANDARD"


def pytest_collection_modifyitems(config, items):
    if _SERVER is None:
        skip = pytest.mark.skip(reason="PostgreSQL not reachable (set TEST_POSTGRES_URL)")
        for item in items:
            if "tests/whatsapp/test_conversation" in str(item.fspath).replace("\\", "/"):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def wa_engine():
    with scratch_database("csl_wa") as url:
        command.upgrade(alembic_config(url), "head")
        eng = create_engine(url)
        yield eng
        eng.dispose()


@pytest.fixture(scope="session")
def wa_factory(wa_engine):
    return sessionmaker(bind=wa_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session")
def wa_orgs(wa_factory, wa_engine):
    from app.models.channel import ChannelAccount
    from scripts.seed import seed

    org_ids = seed(wa_factory)["org_ids"]
    db = wa_factory()  # owner session: channel_account is owner-written
    db.add_all([ChannelAccount(phone_number_id=PNID_PROT, organization_id=org_ids["luzviva"]),
                ChannelAccount(phone_number_id=PNID_STD, organization_id=org_ids["aguazul"])])
    db.commit()
    db.close()
    return {"protective": org_ids["luzviva"], "standard": org_ids["aguazul"]}


_phones = itertools.count(584120000001)
_ids = itertools.count(1)


class Bot:
    """Talk to the bot as one resident; read what it sent back."""

    def __init__(self, factory, engine, pnid: str, adapter, extractor=None):
        self.factory, self.engine, self.pnid = factory, engine, pnid
        self.adapter, self.extractor = adapter, extractor
        self.phone = str(next(_phones))
        self.seen = 0
        if getattr(adapter, "_counter", None) == 0:
            adapter._counter = next(_ids) * 1000  # fake wamids unique across tests

    # --- sending ---------------------------------------------------------
    def _payload(self, message: dict) -> dict:
        return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
            "field": "messages",
            "value": {"messaging_product": "whatsapp",
                      "metadata": {"display_phone_number": "580000", "phone_number_id": self.pnid},
                      "contacts": [{"profile": {"name": "Vecina"}, "wa_id": self.phone}],
                      "messages": [{"from": self.phone, **message}]}}]}]}

    def store(self, payload: dict, provider_id: str, event_type: str = "message",
              received_at=None) -> str:
        from app.models.system import InboundEvent

        db = self.factory()
        ev = InboundEvent(event_type=event_type, channel_account_id=self.pnid,
                          provider_message_id=provider_id, payload_json=payload,
                          signature_valid=True)
        if received_at is not None:
            ev.received_at = received_at
        db.add(ev)
        db.commit()
        db.close()
        return ev.id

    def _msg(self, body: dict, ts: int | None = None) -> str:
        mid = f"wamid.IN{next(_ids)}"
        self.last_mid = mid
        self.store(self._payload({"id": mid, "timestamp": str(ts or int(time.time())), **body}),
                   mid)
        return mid

    def say(self, text_: str, run: bool = True, ts: int | None = None) -> list[dict]:
        self._msg({"type": "text", "text": {"body": text_}}, ts)
        return self.run() if run else []

    def tap(self, choice_id: str, title: str = "", run: bool = True) -> list[dict]:
        self._msg({"type": "interactive", "interactive": {
            "type": "list_reply", "list_reply": {"id": choice_id, "title": title}}})
        return self.run() if run else []

    def pick(self, title_part: str) -> list[dict]:
        """Tap the option of the last question whose title contains ``title_part``."""
        opts = self.options()
        for o in opts:
            if title_part.lower() in o["title"].lower():
                return self.tap(o["id"], o["title"])
        raise AssertionError(f"no option like {title_part!r} in {[o['title'] for o in opts]}")

    def media(self) -> list[dict]:
        self._msg({"type": "audio", "audio": {"id": "media-1", "mime_type": "audio/ogg"}})
        return self.run()

    def run(self) -> list[dict]:
        from scripts.worker import run_cycle

        run_cycle(self.adapter, self.extractor, 50, session_factory=self.factory)
        return self.new()

    # --- reading ---------------------------------------------------------
    def mine(self) -> list[dict]:
        return [m for m in self.adapter.sent if m["to"] == self.phone]

    def new(self) -> list[dict]:
        mine = self.mine()
        out, self.seen = mine[self.seen:], len(mine)
        return out

    def last(self) -> dict:
        return self.mine()[-1]["message"]

    def options(self) -> list[dict]:
        m = self.last()
        if m["kind"] == "buttons":
            return m["buttons"]
        if m["kind"] == "list":
            return m["rows"]
        return []

    def report(self) -> dict:
        """The newest report of this resident (owner read, bypasses RLS)."""
        return self.owner(
            "SELECT r.* FROM report r JOIN reporter_key k ON k.id = r.reporter_key_id "
            "JOIN contact_endpoint ce ON ce.id = k.contact_endpoint_id "
            "JOIN conversation c ON c.contact_endpoint_id = ce.id "
            "JOIN message m ON m.conversation_id = c.id "
            "WHERE m.provider_message_id = :p ORDER BY r.created_at DESC LIMIT 1",
            p=self.last_mid)[0]

    def conversation(self) -> dict:
        return self.owner(
            "SELECT c.* FROM conversation c JOIN message m ON m.conversation_id = c.id "
            "WHERE m.provider_message_id = :p", p=self.last_mid)[0]

    def owner(self, sql: str, **kw):
        with self.engine.connect() as c:
            return c.execute(text(sql), kw).mappings().all()


@pytest.fixture()
def bot(wa_factory, wa_engine, wa_orgs):
    from app.whatsapp.adapter import FakeAdapter

    adapter = FakeAdapter()

    def _make(profile: str = "protective", extractor=None, adapter_=None):
        return Bot(wa_factory, wa_engine, PNID_PROT if profile == "protective" else PNID_STD,
                   adapter_ or adapter, extractor)

    return _make
