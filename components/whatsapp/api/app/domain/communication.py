"""Reporter communication (DOM-060..064): permissions, the outbound gate, refresh
prompts, area broadcasts, opt-out.

Blocked intents are dropped and counted; they never create staff tasks (DOM-061).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Optional, Sequence

from app.domain.errors import Forbidden, ValidationFailed
from app.domain.providers import activity_serves
from app.domain.reports import is_aggregatable
from app.domain.types import (
    Activity,
    ActivityStatus,
    Area,
    DomainContext,
    GateBlockReason,
    GateResult,
    Need,
    NeedState,
    OutboundIntent,
    OutboundPurpose,
    Permission,
    PermissionPurpose,
    ProviderOrganization,
    Report,
    ReporterCommState,
    Role,
    SentMessage,
)

PURPOSE_PERMISSION: dict[OutboundPurpose, Optional[PermissionPurpose]] = {
    OutboundPurpose.conversation_reply: None,
    OutboundPurpose.optout_confirmation: None,
    OutboundPurpose.refresh_prompt: PermissionPurpose.refresh_prompts,
    OutboundPurpose.area_broadcast: PermissionPurpose.area_broadcasts,
}

BUSINESS_INITIATED = frozenset({OutboundPurpose.refresh_prompt, OutboundPurpose.area_broadcast})


@dataclass(frozen=True)
class CommPolicy:
    version: str = "comm-policy-1"
    session_window: timedelta = timedelta(hours=24)
    max_business_per_day: int = 3
    max_broadcasts_per_week: int = 2
    refresh_interval: timedelta = timedelta(hours=72)
    max_refresh_per_need: int = 3
    refresh_template_id: str = "refresh_prompt_v1"


DEFAULT_COMM_POLICY = CommPolicy()


# ---------------------------------------------------------------------------
# Permissions and opt-out (DOM-060/064)
# ---------------------------------------------------------------------------


def grant_permission(reporter_key: str, purpose: PermissionPurpose, notice_version: str, now: datetime) -> Permission:
    return Permission(reporter_key, purpose, notice_version, now)


def withdraw_permission(perm: Permission, now: datetime) -> Permission:
    """Stops only that purpose, immediately for future use."""
    if perm.withdrawn_at is not None:
        return perm
    return replace(perm, withdrawn_at=now)


def has_permission(perms: Iterable[Permission], key: str, purpose: PermissionPurpose, now: datetime) -> bool:
    return any(p.reporter_key == key and p.purpose is purpose and p.active_at(now) for p in perms)


def process_optout(
    state: ReporterCommState, permissions: Iterable[Permission], now: datetime
) -> tuple[ReporterCommState, list[Permission], OutboundIntent]:
    """``BAJA``: withdraw every permission and stop all outbound except the
    confirmation, which is returned as the only intent."""
    new_state = replace(state, opted_out_at=now, last_inbound_at=now)
    withdrawn = [withdraw_permission(p, now) for p in permissions if p.reporter_key == state.reporter_key]
    confirm = OutboundIntent(state.reporter_key, OutboundPurpose.optout_confirmation, now)
    return new_state, withdrawn, confirm


# ---------------------------------------------------------------------------
# Outbound gate (DOM-061)
# ---------------------------------------------------------------------------


def check_gate(
    intent: OutboundIntent,
    permissions: Iterable[Permission],
    state: ReporterCommState,
    sent: Iterable[SentMessage],
    now: datetime,
    policy: CommPolicy = DEFAULT_COMM_POLICY,
) -> GateResult:
    if intent.reporter_key != state.reporter_key:
        raise ValidationFailed("intent and state are for different reporters")
    if state.opted_out_at is not None and state.opted_out_at <= now:
        if intent.purpose is not OutboundPurpose.optout_confirmation:
            return GateResult(False, GateBlockReason.opted_out)
    needed = PURPOSE_PERMISSION[intent.purpose]
    if needed is not None and not has_permission(permissions, intent.reporter_key, needed, now):
        return GateResult(False, GateBlockReason.no_permission)
    in_window = state.last_inbound_at is not None and now - state.last_inbound_at < policy.session_window
    if not in_window and intent.template_id is None:
        return GateResult(False, GateBlockReason.outside_window_no_template)
    if intent.purpose in BUSINESS_INITIATED:
        mine = [s for s in sent if s.reporter_key == intent.reporter_key]
        day = [s for s in mine if s.purpose in BUSINESS_INITIATED and now - s.sent_at < timedelta(days=1)]
        if len(day) >= policy.max_business_per_day:
            return GateResult(False, GateBlockReason.rate_limited)
        if intent.purpose is OutboundPurpose.area_broadcast:
            week = [s for s in mine if s.purpose is OutboundPurpose.area_broadcast and now - s.sent_at < timedelta(days=7)]
            if len(week) >= policy.max_broadcasts_per_week:
                return GateResult(False, GateBlockReason.rate_limited)
    return GateResult(True)


@dataclass(frozen=True)
class GateBatchResult:
    allowed: tuple[OutboundIntent, ...]
    blocked_counts: Mapping[GateBlockReason, int]


def gate_batch(
    intents: Sequence[OutboundIntent],
    permissions: Iterable[Permission],
    states: Mapping[str, ReporterCommState],
    sent: Iterable[SentMessage],
    now: datetime,
    policy: CommPolicy = DEFAULT_COMM_POLICY,
) -> GateBatchResult:
    """Gate several intents; allowed ones count toward later rate limits."""
    perms = list(permissions)
    log = list(sent)
    allowed: list[OutboundIntent] = []
    blocked: Counter = Counter()
    for intent in intents:
        state = states.get(intent.reporter_key, ReporterCommState(intent.reporter_key))
        res = check_gate(intent, perms, state, log, now, policy)
        if res.allowed:
            allowed.append(intent)
            log.append(SentMessage(intent.reporter_key, intent.purpose, now))
        else:
            blocked[res.reason] += 1
    return GateBatchResult(tuple(allowed), dict(blocked))


# ---------------------------------------------------------------------------
# Refresh prompts (DOM-062)
# ---------------------------------------------------------------------------


def refresh_due(need: Need, now: datetime, policy: CommPolicy = DEFAULT_COMM_POLICY) -> bool:
    if not need.is_open or need.refresh_prompts_sent >= policy.max_refresh_per_need:
        return False
    ref = max(need.last_confirmed_at, need.last_prompted_at or need.last_confirmed_at)
    return now - ref >= policy.refresh_interval


def schedule_refresh_prompts(
    reports: Iterable[Report],
    permissions: Iterable[Permission],
    states: Mapping[str, ReporterCommState],
    now: datetime,
    policy: CommPolicy = DEFAULT_COMM_POLICY,
) -> list[OutboundIntent]:
    """One refresh intent per due need (active or stale), for permitted reporters
    who have not opted out. Intents still pass through the gate."""
    perms = list(permissions)
    out: list[OutboundIntent] = []
    for r in reports:
        if r.reporter_key is None or not is_aggregatable(r):
            continue
        st = states.get(r.reporter_key)
        if st is not None and st.opted_out_at is not None:
            continue
        if not has_permission(perms, r.reporter_key, PermissionPurpose.refresh_prompts, now):
            continue
        for n in r.needs:
            if refresh_due(n, now, policy):
                out.append(
                    OutboundIntent(
                        r.reporter_key,
                        OutboundPurpose.refresh_prompt,
                        now,
                        template_id=policy.refresh_template_id,
                        need_id=n.id,
                    )
                )
    return out


def record_prompt_sent(need: Need, now: datetime) -> Need:
    return replace(need, refresh_prompts_sent=need.refresh_prompts_sent + 1, last_prompted_at=now)


# ---------------------------------------------------------------------------
# Area broadcasts (DOM-063)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BroadcastTemplate:
    id: str
    text: str  # e.g. "Punto de agua en {lugar}, {horario}, organizado por {organizacion}"
    text_without_provider: str  # e.g. "Punto de agua en {lugar}, {horario}"


@dataclass(frozen=True)
class ApprovedBroadcast:
    id: str
    template_id: str
    activity_id: str
    text: str
    approved_by: str
    approved_at: datetime


class _Strict(dict):
    def __missing__(self, key):
        raise ValidationFailed(f"template placeholder {{{key}}} has no value")


def approve_broadcast(
    ctx: DomainContext,
    broadcast_id: str,
    template: BroadcastTemplate,
    activity: Activity,
    provider: ProviderOrganization,
    place_name: str,
    now: datetime,
) -> ApprovedBroadcast:
    """A coordinator approves template text; the provider name appears only if the
    provider allows it."""
    if not (ctx.has(Role.coordinator) or ctx.has(Role.org_admin)):
        raise Forbidden("only a coordinator can approve broadcasts")
    if provider.id != activity.provider_id or provider.org_id != ctx.org_id:
        raise Forbidden("activity/provider mismatch")
    if activity.status not in (ActivityStatus.planned, ActivityStatus.active):
        raise ValidationFailed("broadcasts are for planned or active activities")
    values = {"lugar": place_name, "horario": activity.schedule.description}
    if provider.name_in_broadcasts_allowed:
        text = template.text.format_map(_Strict(values, organizacion=provider.name))
    else:
        text = template.text_without_provider.format_map(_Strict(values))
    return ApprovedBroadcast(broadcast_id, template.id, activity.id, text, ctx.actor_id, now)


def select_broadcast_recipients(
    activity: Activity,
    reports: Iterable[Report],
    permissions: Iterable[Permission],
    states: Mapping[str, ReporterCommState],
    sent: Iterable[SentMessage],
    areas: Mapping[str, Area],
    now: datetime,
    policy: CommPolicy = DEFAULT_COMM_POLICY,
) -> list[str]:
    """Permitted reporters with a matching active need in the activity's areas,
    capped at ``max_broadcasts_per_week`` per reporter."""
    perms = list(permissions)
    log = list(sent)
    keys: set[str] = set()
    for r in reports:
        if r.reporter_key is None or not is_aggregatable(r):
            continue
        if not activity_serves(activity, r.area_id, areas):
            continue
        if not any(
            n.category is activity.category and n.state is NeedState.active and n.replaced_by_id is None
            for n in r.needs
        ):
            continue
        keys.add(r.reporter_key)
    out = []
    for key in sorted(keys):
        st = states.get(key)
        if st is not None and st.opted_out_at is not None:
            continue
        if not has_permission(perms, key, PermissionPurpose.area_broadcasts, now):
            continue
        recent = sum(
            1
            for s in log
            if s.reporter_key == key
            and s.purpose is OutboundPurpose.area_broadcast
            and now - s.sent_at < timedelta(days=7)
        )
        if recent >= policy.max_broadcasts_per_week:
            continue
        out.append(key)
    return out
