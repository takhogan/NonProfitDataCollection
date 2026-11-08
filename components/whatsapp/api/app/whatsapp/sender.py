"""Deliver ``outbox_message`` rows through the WhatsApp adapter (OPW-030..035).

Per organization (tenant transaction, worker role):

1. **Reconcile** rows stuck in ``sending`` past their deadline: a send that may
   have reached Meta is never resent blindly (OPW-032). If no status webhook
   named it (``biz_opaque_callback_data`` = outbox id), it becomes a visible
   ``failed`` row with reason ``uncertain_unconfirmed``.
2. **Gate and claim** due ``pending`` rows, highest ``priority`` first
   (resident replies before refresh prompts before broadcasts, OPW-034):
   - opted-out endpoints get nothing but the opt-out confirmation (OPW-018);
   - free-form messages only inside the 24-hour window, otherwise an approved
     template; a missing template is a terminal failure (OPW-031);
   claimed rows move to ``sending`` and the transaction commits.
3. **Send outside any transaction** (DB-032), through a token bucket.
4. **Record** the outcome: ``sent`` + provider id + an outbound ``message``
   row; retryable errors back off (max 8 attempts); permanent errors fail;
   uncertain ones stay ``sending`` until reconciled.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.crypto import decrypt
from app.db import system_transaction, tenant_transaction
from app.models.base import utcnow
from app.models.channel import ChannelAccount
from app.models.org import Organization
from app.models.reporting import ContactEndpoint, Message
from app.models.system import OutboxMessage
from app.whatsapp.adapter import SendError, WhatsAppAdapter

log = logging.getLogger("whatsapp.sender")

ACTOR = "worker:sender"
MAX_SEND_ATTEMPTS = 8


class TokenBucket:
    """Process-wide send rate limit (OPW-034)."""

    def __init__(self, rate: float, burst: int):
        self.rate, self.capacity = max(rate, 0.001), max(burst, 1)
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self, sleep=time.sleep) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                sleep((1 - self.tokens) / self.rate)


_bucket: TokenBucket | None = None


def bucket() -> TokenBucket:
    global _bucket
    if _bucket is None:
        s = get_settings()
        _bucket = TokenBucket(s.whatsapp_send_rate_per_second, s.whatsapp_send_burst)
    return _bucket


def templates() -> dict:
    try:
        data = json.loads(get_settings().whatsapp_templates_json or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        log.error("WHATSAPP_TEMPLATES_JSON is not valid JSON")
        return {}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class _Job:
    outbox_id: str
    phone_number_id: str
    to: str
    message: dict


def _org_ids(session_factory=None) -> list[str]:
    kw = {"session": session_factory()} if session_factory else {}
    with system_transaction(ACTOR, **kw) as db:
        ids = set(db.scalars(select(ChannelAccount.organization_id).where(
            ChannelAccount.status == "active")))
        fallback = get_settings().whatsapp_fallback_org_name
        if fallback:
            ids.update(db.scalars(select(Organization.id).where(Organization.name == fallback)))
        return sorted(ids)


def _default_number(db, org_id: str) -> str | None:
    return db.scalar(select(ChannelAccount.phone_number_id).where(
        ChannelAccount.organization_id == org_id, ChannelAccount.status == "active")
        .order_by(ChannelAccount.created_at.asc()).limit(1))


def _claim(org_id: str, limit: int, now: datetime, session_factory=None) -> list[_Job]:
    s = get_settings()
    window = timedelta(hours=s.whatsapp_session_window_hours)
    reconcile = timedelta(minutes=s.uncertain_send_reconcile_minutes)
    tpl = templates()
    kw = {"session": session_factory()} if session_factory else {}
    jobs: list[_Job] = []
    with tenant_transaction(org_id, ACTOR, "system", **kw) as db:
        # 1. reconcile expired uncertain sends (never resend)
        for row in db.scalars(select(OutboxMessage).where(
                OutboxMessage.organization_id == org_id, OutboxMessage.status == "sending",
                OutboxMessage.next_attempt_at <= now).with_for_update(skip_locked=True)):
            row.status = "failed"
            row.block_reason = "uncertain_unconfirmed"
            row.last_error = row.last_error or "send outcome unknown; not resent"
            log.error("outbox %s: uncertain send not confirmed, marked failed", row.id)

        # 2. gate and claim
        rows = list(db.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.organization_id == org_id, OutboxMessage.status == "pending",
                   OutboxMessage.next_attempt_at <= now)
            .order_by(OutboxMessage.priority.desc(), OutboxMessage.created_at.asc())
            .limit(limit).with_for_update(skip_locked=True)))
        for row in rows:
            ep = db.get(ContactEndpoint, row.contact_endpoint_id) if row.contact_endpoint_id else None
            msg = dict(row.message_json or {})
            pnid = msg.pop("_pnid", None) or _default_number(db, org_id)
            if ep is None or ep.status == "deleted" or not ep.encrypted_address or not pnid:
                row.status, row.block_reason = "blocked", "no_recipient"
                continue
            if ep.status == "opted_out" and row.purpose != "opt_out_confirmation":
                row.status, row.block_reason = "blocked", "opted_out"
                continue
            if msg.get("kind") == "template":
                spec = tpl.get(msg.get("key") or row.template_name or "")
                if not spec or not spec.get("name"):
                    row.status, row.block_reason = "failed", "template_missing"
                    row.last_error = f"no approved template for {msg.get('key')!r}"
                    continue
                msg = {"kind": "template", "name": spec["name"],
                       "language": spec.get("language", "es"),
                       "params": msg.get("params") or list(row.template_params.get("params", []))}
            else:
                last = _aware(ep.last_activity_at)
                if last is None or now - last >= window:
                    row.status, row.block_reason = "blocked", "outside_window_no_template"
                    continue
            row.status = "sending"
            row.attempts += 1
            row.next_attempt_at = now + reconcile  # reconcile deadline if we crash mid-send
            jobs.append(_Job(row.id, pnid, decrypt(ep.encrypted_address), msg))
    return jobs


def _record(org_id: str, results: list[tuple[_Job, object]], now: datetime,
            session_factory=None) -> None:
    reconcile = timedelta(minutes=get_settings().uncertain_send_reconcile_minutes)
    kw = {"session": session_factory()} if session_factory else {}
    with tenant_transaction(org_id, ACTOR, "system", **kw) as db:
        for job, outcome in results:
            row = db.get(OutboxMessage, job.outbox_id)
            if row is None or row.status != "sending":
                continue  # a status webhook got here first
            if isinstance(outcome, SendError):
                row.last_error = str(outcome)[:500]
                if outcome.uncertain:
                    row.block_reason = "uncertain"
                    row.next_attempt_at = now + reconcile
                elif outcome.retryable and row.attempts < MAX_SEND_ATTEMPTS:
                    row.status = "pending"
                    row.next_attempt_at = now + timedelta(seconds=min(5 * 2 ** row.attempts, 3600))
                else:
                    row.status = "failed"
                continue
            row.status = "sent"
            row.provider_message_id = outcome.provider_message_id
            row.sent_at = now
            row.block_reason = None
            row.last_error = None
            if row.conversation_id and db.scalar(select(Message.id).where(
                    Message.channel_account_id == job.phone_number_id,
                    Message.provider_message_id == outcome.provider_message_id)) is None:
                db.add(Message(organization_id=org_id, conversation_id=row.conversation_id,
                               channel_account_id=job.phone_number_id,
                               provider_message_id=outcome.provider_message_id,
                               direction="outbound", sent_at=now, delivery_status="sent"))


def send_pending(adapter: WhatsAppAdapter, batch_size: int, now: datetime | None = None,
                 session_factory=None, rate: TokenBucket | None = None) -> int:
    """Send due outbox rows for every organization with a channel. Returns attempts."""
    now = now or utcnow()
    limiter = rate or bucket()
    total = 0
    for org_id in _org_ids(session_factory):
        jobs = _claim(org_id, batch_size, now, session_factory)
        if not jobs:
            continue
        results = []
        for job in jobs:
            limiter.take()
            try:
                outcome = adapter.send(phone_number_id=job.phone_number_id, to=job.to,
                                       message=job.message, callback_data=job.outbox_id)
            except SendError as exc:
                outcome = exc
                log.warning("outbox %s send error (uncertain=%s retryable=%s): %s",
                            job.outbox_id, exc.uncertain, exc.retryable, exc)
            except Exception as exc:  # noqa: BLE001 - unknown: assume it may have gone out
                outcome = SendError(f"unexpected {type(exc).__name__}", uncertain=True)
            results.append((job, outcome))
        _record(org_id, results, now, session_factory)
        total += len(jobs)
    return total
