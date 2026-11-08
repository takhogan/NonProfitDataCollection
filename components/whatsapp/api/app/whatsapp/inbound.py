"""Route stored webhook events (``inbound_event``) into conversations and statuses.

Per event (OPW-001..005):

1. claim it in a tenant-less system transaction (attempt count, no network);
2. for every message and status in the payload (all entries, all changes),
   find the owning organization via ``channel_account`` and work inside a
   tenant transaction under the worker role, so RLS applies;
3. optional OpenAI extraction runs between two transactions, never inside one;
4. finish with a terminal state: ``processed``, ``ignored`` (with a reason) or
   ``failed`` after ``MAX_ATTEMPTS``. Processed and ignored payloads are reduced
   to non-identifying metadata, so phone numbers and message text do not stay
   in the inbox.

Idempotency: the ``message`` table is unique on (channel account, provider
message id), so a replayed or re-processed message never runs the engine twice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import system_transaction, tenant_transaction
from app.models.base import utcnow
from app.models.channel import ChannelAccount
from app.models.org import Organization
from app.models.outreach import Campaign
from app.models.privacy import PrivacyProfileVersion
from app.models.reporting import Message
from app.models.system import InboundEvent, OutboxMessage
from app.whatsapp.engine import (
    Engine, EngineContext, Inbound, record_inbound_message, resolve_conversation,
)
from app.whatsapp.extraction import Extractor

log = logging.getLogger("whatsapp.inbound")

MAX_ATTEMPTS = 8
ACTOR = "worker:whatsapp"
MEDIA_TYPES = {"image", "audio", "video", "document", "sticker", "voice"}
_DELIVERY_ORDER = {"received": 0, "queued": 0, "sent": 1, "delivered": 2, "read": 3}


class SkipEvent(Exception):
    """Terminal, non-error outcome (``ignored``) with a redacted reason."""


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------


@dataclass
class MessageItem:
    phone_number_id: str
    sender: str
    inbound: Inbound


@dataclass
class StatusItem:
    phone_number_id: str
    wamid: str | None
    status: str
    callback_data: str | None
    error: str | None


def _ts(raw) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def to_inbound(msg: dict) -> Inbound:
    mid = msg.get("id") or ""
    t = msg.get("type")
    at = _ts(msg.get("timestamp"))
    if t == "text":
        return Inbound(mid, "text", text=(msg.get("text") or {}).get("body", ""), received_at=at)
    if t == "interactive":
        inter = msg.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return Inbound(mid, "choice", choice_id=reply.get("id"), choice_title=reply.get("title"),
                       received_at=at)
    if t == "button":  # quick-reply button on a template
        b = msg.get("button") or {}
        return Inbound(mid, "choice", choice_id=b.get("payload"), choice_title=b.get("text"),
                       received_at=at)
    if t == "location":
        loc = msg.get("location") or {}
        try:
            lat, lon = float(loc.get("latitude")), float(loc.get("longitude"))
        except (TypeError, ValueError):
            return Inbound(mid, "unsupported", received_at=at)
        return Inbound(mid, "location", lat=lat, lon=lon, received_at=at)
    if t in MEDIA_TYPES:
        return Inbound(mid, "media", received_at=at)
    if t in ("reaction", "system", "ephemeral", "unsupported", None):
        return Inbound(mid, "ignore", received_at=at)
    return Inbound(mid, "unsupported", received_at=at)


def parse_payload(payload: dict) -> tuple[list[MessageItem], list[StatusItem]]:
    """Every message and status in every entry/change (not just item [0])."""
    msgs: list[MessageItem] = []
    stats: list[StatusItem] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            pnid = (value.get("metadata") or {}).get("phone_number_id")
            if not pnid:
                continue
            for m in value.get("messages") or []:
                if m.get("from") and m.get("id"):
                    msgs.append(MessageItem(pnid, m["from"], to_inbound(m)))
            for s in value.get("statuses") or []:
                err = None
                if s.get("errors"):
                    e = s["errors"][0]
                    err = f"code={e.get('code')} {str(e.get('title', ''))[:100]}"
                stats.append(StatusItem(pnid, s.get("id"), s.get("status") or "",
                                        s.get("biz_opaque_callback_data"), err))
    return msgs, stats


def redacted_summary(payload: dict) -> dict:
    msgs, stats = parse_payload(payload)
    return {"redacted": True, "messages": len(msgs),
            "message_kinds": sorted({m.inbound.kind for m in msgs}),
            "statuses": sorted({s.status for s in stats})}


# ---------------------------------------------------------------------------
# Tenant helpers
# ---------------------------------------------------------------------------


def channel_for(db: Session, phone_number_id: str) -> ChannelAccount | None:
    return db.scalar(select(ChannelAccount).where(
        ChannelAccount.phone_number_id == phone_number_id, ChannelAccount.status == "active"))


def _context(db: Session, ch: ChannelAccount, sender: str, now: datetime) -> EngineContext:
    s = get_settings()
    org = db.get(Organization, ch.organization_id)
    campaign = db.get(Campaign, ch.campaign_id) if ch.campaign_id else db.scalar(
        select(Campaign).where(Campaign.organization_id == ch.organization_id,
                               Campaign.status == "active")
        .order_by(Campaign.starts_at.desc()).limit(1))
    profile = db.scalar(select(PrivacyProfileVersion).where(
        PrivacyProfileVersion.organization_id == ch.organization_id,
        PrivacyProfileVersion.status == "active"))
    if profile is None:
        raise SkipEvent("no_active_privacy_profile")
    res = resolve_conversation(db, ch.organization_id, campaign, sender, now)
    return EngineContext(
        org_id=ch.organization_id,
        org_name=org.name if org else s.pilot_org_name,
        identity=campaign.display_identity if campaign else "Metron Reporter",
        phone_number_id=ch.phone_number_id,
        campaign=campaign, profile=profile, endpoint=res.endpoint,
        conversation=res.conversation, now=now, referral_text=s.urgent_referral_text,
        resume_hours=s.conversation_resume_hours,
    )


def _seen(db: Session, item: MessageItem) -> bool:
    return db.scalar(select(Message.id).where(
        Message.channel_account_id == item.phone_number_id,
        Message.provider_message_id == item.inbound.provider_message_id)) is not None


def handle_message(item: MessageItem, ch: ChannelAccount, extractor: Extractor | None,
                   now: datetime, session_factory=None) -> None:
    kw = {"session": session_factory()} if session_factory else {}
    request = None
    if extractor is not None and item.inbound.kind == "text":
        with tenant_transaction(ch.organization_id, ACTOR, "system", **kw) as db:
            if _seen(db, item):
                return
            ctx = _context(db, ch, item.sender, now)
            request = Engine(db, ctx).wants_extraction(item.inbound)
        kw = {"session": session_factory()} if session_factory else {}

    extraction = None
    if request is not None:
        # Outside any transaction (DB-032). Redaction happens in the extractor.
        extraction = extractor.extract(question=request[0], answer=request[1])

    with tenant_transaction(ch.organization_id, ACTOR, "system", **kw) as db:
        ctx = _context(db, ch, item.sender, now)
        if not record_inbound_message(db, ch.organization_id, ctx.conversation,
                                      ch.phone_number_id, item.inbound):
            return  # replay: already handled (OPW-002)
        if item.inbound.kind == "ignore":
            ctx.endpoint.last_activity_at = now
            return
        Engine(db, ctx).handle(item.inbound, extraction)


def apply_status(db: Session, org_id: str, st: StatusItem, now: datetime) -> None:
    """Monotonic delivery status on ``message``; reconcile uncertain sends (OPW-032/040)."""
    row = None
    if st.wamid:
        row = db.scalar(select(OutboxMessage).where(
            OutboxMessage.organization_id == org_id,
            OutboxMessage.provider_message_id == st.wamid))
    if row is None and st.callback_data:
        row = db.scalar(select(OutboxMessage).where(
            OutboxMessage.organization_id == org_id, OutboxMessage.id == st.callback_data))
        if row is not None and row.provider_message_id is None and st.wamid:
            # An uncertain send did reach Meta: record it, never resend.
            row.provider_message_id = st.wamid
            if row.status in ("sending", "pending", "failed") and st.status != "failed":
                row.status = "sent"
                row.sent_at = row.sent_at or now
                row.block_reason = None
    if row is not None and st.status == "failed":
        row.status = "failed"
        row.last_error = (st.error or "provider reported failure")[:500]
    if row is not None and row.provider_message_id and row.conversation_id:
        msg = db.scalar(select(Message).where(
            Message.channel_account_id == st.phone_number_id,
            Message.provider_message_id == row.provider_message_id))
        if msg is None:
            msg = Message(organization_id=org_id, conversation_id=row.conversation_id,
                          channel_account_id=st.phone_number_id,
                          provider_message_id=row.provider_message_id, direction="outbound",
                          sent_at=row.sent_at or now, delivery_status="sent")
            db.add(msg)
        if st.status == "failed":
            msg.delivery_status = "failed"
        elif (msg.delivery_status != "failed" and st.status in _DELIVERY_ORDER
              and _DELIVERY_ORDER[st.status] > _DELIVERY_ORDER.get(msg.delivery_status, 0)):
            msg.delivery_status = st.status


# ---------------------------------------------------------------------------
# Event loop pieces
# ---------------------------------------------------------------------------


def _due(event: InboundEvent, now: datetime) -> bool:
    if event.status != "failed":
        return True
    wait = min(2 ** event.attempts, 3600)
    updated = event.updated_at or event.received_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return now - updated >= timedelta(seconds=wait)


def pending_event_ids(batch_size: int, now: datetime, session_factory=None) -> list[str]:
    kw = {"session": session_factory()} if session_factory else {}
    with system_transaction(ACTOR, **kw) as db:
        rows = list(db.scalars(
            select(InboundEvent)
            .where(InboundEvent.processed_at.is_(None),
                   InboundEvent.status.in_(("received", "failed")),
                   InboundEvent.attempts < MAX_ATTEMPTS)
            .order_by(InboundEvent.received_at.asc())
            .limit(batch_size * 3)))
        return [e.id for e in rows if _due(e, now)][:batch_size]


def oldest_pending_at(session_factory=None) -> datetime | None:
    kw = {"session": session_factory()} if session_factory else {}
    with system_transaction(ACTOR, **kw) as db:
        ts = db.scalar(select(func.min(InboundEvent.received_at)).where(
            InboundEvent.processed_at.is_(None), InboundEvent.event_type == "message",
            InboundEvent.status.in_(("received", "failed")),
            InboundEvent.attempts < MAX_ATTEMPTS))
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def process_event(event_id: str, extractor: Extractor | None, now: datetime | None = None,
                  session_factory=None) -> str:
    """Process one stored event end to end. Returns its final status."""
    now = now or utcnow()
    kw = lambda: {"session": session_factory()} if session_factory else {}  # noqa: E731
    with system_transaction(ACTOR, **kw()) as db:
        ev = db.get(InboundEvent, event_id)
        if ev is None or ev.processed_at is not None:
            return "skipped"
        ev.attempts += 1
        ev.status = "processing"
        payload = dict(ev.payload_json or {})
        channels = {}
        msgs, stats = parse_payload(payload)
        for pnid in {m.phone_number_id for m in msgs} | {s.phone_number_id for s in stats}:
            ch = channel_for(db, pnid)
            if ch is not None:
                db.expunge(ch)
                channels[pnid] = ch

    status, reason = "processed", None
    try:
        if not msgs and not stats:
            raise SkipEvent("no_messages_or_statuses")
        if not channels:
            raise SkipEvent("unmapped_channel_account")
        for item in msgs:
            ch = channels.get(item.phone_number_id)
            if ch is not None:
                handle_message(item, ch, extractor, now, session_factory)
        by_org: dict[str, list[StatusItem]] = {}
        for st in stats:
            ch = channels.get(st.phone_number_id)
            if ch is not None:
                by_org.setdefault(ch.organization_id, []).append(st)
        for org_id, items in by_org.items():
            with tenant_transaction(org_id, ACTOR, "system", **kw()) as db:
                for st in items:
                    apply_status(db, org_id, st, now)
    except SkipEvent as skip:
        status, reason = "ignored", str(skip)
    except Exception as exc:  # noqa: BLE001 - keep the loop alive, record redacted reason
        log.exception("inbound_event %s failed", event_id)
        status, reason = "failed", f"{type(exc).__name__}"

    with system_transaction(ACTOR, **kw()) as db:
        ev = db.get(InboundEvent, event_id)
        ev.last_error = reason
        if status == "failed":
            ev.status = "failed"
            if ev.attempts >= MAX_ATTEMPTS:
                ev.processed_at = now  # terminal and visible to staff (OPW-001/004)
        else:
            ev.status = status
            ev.processed_at = now
            # No raw phone numbers or message text left in the inbox (NFR-09).
            ev.payload_json = redacted_summary(payload)
    return status


def queue_surge_holding(batch_size: int, now: datetime, session_factory=None) -> int:
    """Surge mode (OPW-035): one holding reply per waiting conversation."""
    oldest = oldest_pending_at(session_factory)
    lag = get_settings().surge_lag_seconds
    if oldest is None or (now - oldest).total_seconds() <= lag:
        return 0
    kw = lambda: {"session": session_factory()} if session_factory else {}  # noqa: E731
    with system_transaction(ACTOR, **kw()) as db:
        events = list(db.scalars(select(InboundEvent).where(
            InboundEvent.processed_at.is_(None), InboundEvent.event_type == "message",
            InboundEvent.status.in_(("received", "failed")))
            .order_by(InboundEvent.received_at.asc()).limit(batch_size * 10)))
        work = []
        for ev in events:
            msgs, _ = parse_payload(ev.payload_json or {})
            for m in msgs:
                ch = channel_for(db, m.phone_number_id)
                if ch is not None and m.inbound.kind != "ignore":
                    db.expunge(ch)
                    work.append((ch, m.sender, m.inbound.received_at or now))
    queued, seen = 0, set()
    for ch, sender, received_at in work:
        if (ch.organization_id, sender) in seen:
            continue
        seen.add((ch.organization_id, sender))
        try:
            with tenant_transaction(ch.organization_id, ACTOR, "system", **kw()) as db:
                ctx = _context(db, ch, sender, now)
                # The resident wrote at received_at, so the 24 h window is open.
                last = ctx.endpoint.last_activity_at
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if last is None or last < received_at:
                    ctx.endpoint.last_activity_at = received_at
                if Engine(db, ctx).queue_holding(oldest):
                    queued += 1
        except SkipEvent:
            continue
    if queued:
        log.warning("surge mode: lag %.0fs, queued %s holding replies",
                    (now - oldest).total_seconds(), queued)
    return queued
