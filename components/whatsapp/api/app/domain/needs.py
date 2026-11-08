"""Need lifecycle (DOM-020..023).

    active -> stale -> resolved_by_reporter | withdrawn | expired

Only the reporter (refresh replies) or the expiry timer changes a need. Provider
activity, staff, and service-restoration observations never do (DOM-022).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from app.domain.errors import InvalidTransition
from app.domain.types import Need, NeedState, ObservationInput, Service, ServiceStatus, TimePrecision


class NeedActor(str, Enum):
    reporter = "reporter"
    system = "system"  # timers
    provider = "provider"
    staff = "staff"


@dataclass(frozen=True)
class NeedPolicy:
    version: str = "need-policy-1"
    refresh_period: timedelta = timedelta(hours=72)
    expiry_period: timedelta = timedelta(days=14)


DEFAULT_NEED_POLICY = NeedPolicy()

A, S = NeedState.active, NeedState.stale
# DOM-004: the declared transition table; value = actors allowed to make it.
NEED_TRANSITIONS: dict[tuple[NeedState, NeedState], frozenset[NeedActor]] = {
    (A, S): frozenset({NeedActor.system}),
    (S, A): frozenset({NeedActor.reporter}),
    (A, A): frozenset({NeedActor.reporter}),  # refresh "still need it"
    (A, NeedState.resolved_by_reporter): frozenset({NeedActor.reporter}),
    (S, NeedState.resolved_by_reporter): frozenset({NeedActor.reporter}),
    (A, NeedState.withdrawn): frozenset({NeedActor.reporter}),
    (S, NeedState.withdrawn): frozenset({NeedActor.reporter}),
    (A, NeedState.expired): frozenset({NeedActor.system}),
    (S, NeedState.expired): frozenset({NeedActor.system}),
}


def transition_need(need: Need, to: NeedState, actor: NeedActor, now: datetime) -> Need:
    allowed = NEED_TRANSITIONS.get((need.state, to))
    if allowed is None:
        raise InvalidTransition("need", need.state.value, to.value)
    if actor not in allowed:
        raise InvalidTransition("need", need.state.value, to.value, f"actor {actor.value} may not")
    changes: dict = {"state": to, "state_changed_at": now}
    if to is NeedState.active and actor is NeedActor.reporter:
        changes["last_confirmed_at"] = now
    return replace(need, **changes)


def tick_need(need: Need, now: datetime, policy: NeedPolicy = DEFAULT_NEED_POLICY) -> Need:
    """Apply timers: stale after the refresh period, expired after the expiry period,
    both measured from the last reporter confirmation."""
    if not need.is_open:
        return need
    age = now - need.last_confirmed_at
    if age >= policy.expiry_period:
        return transition_need(need, NeedState.expired, NeedActor.system, now)
    if need.state is NeedState.active and age >= policy.refresh_period:
        return transition_need(need, NeedState.stale, NeedActor.system, now)
    return need


@dataclass(frozen=True)
class RefreshReply:
    """Answer to "¿Todavía lo necesitas?" plus the optional service question.

    ``still_needs``: True / False / None (didn't answer that question).
    """

    still_needs: Optional[bool] = None
    withdraw: bool = False
    service: Optional[Service] = None
    service_status: Optional[ServiceStatus] = None


def apply_refresh_reply(
    need: Need, reply: RefreshReply, now: datetime
) -> tuple[Need, Optional[ObservationInput]]:
    """DOM-021/062. Returns the updated need and any new observation to record.

    A service status of ``available`` is recorded as an observation and never
    resolves the need on its own — only "no, I no longer need it" does.
    """
    obs = None
    if reply.service is not None and reply.service_status is not None:
        obs = ObservationInput(
            service=reply.service,
            status=reply.service_status,
            observed_at=now,
            observed_precision=TimePrecision.exact,
        )
    if not need.is_open:
        return need, obs
    if reply.withdraw:
        return transition_need(need, NeedState.withdrawn, NeedActor.reporter, now), obs
    if reply.still_needs is True:
        return transition_need(need, NeedState.active, NeedActor.reporter, now), obs
    if reply.still_needs is False:
        return transition_need(need, NeedState.resolved_by_reporter, NeedActor.reporter, now), obs
    return need, obs


def apply_observation(need: Need, observation: ObservationInput) -> Need:
    """DOM-021: service restoration never resolves a need. Kept as an explicit
    no-op so callers have one place that documents (and tests) the rule."""
    return need
