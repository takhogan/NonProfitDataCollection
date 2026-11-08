"""Providers: vetting, activities, coverage, contact list, alerts (DOM-050..055).

Nothing here changes a need or report (DOM-022): coverage is computed from
indicator cells and activities, and says nothing about whether needs were met.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Optional, Sequence

from app.domain.errors import Forbidden, InvalidTransition, ValidationFailed
from app.domain.indicators import RELATED_SERVICE, ancestor_at_level, within
from app.domain.reports import is_aggregatable
from app.domain.types import (
    Activity,
    ActivityDisplayStatus,
    ActivityStatus,
    ActivityType,
    Alert,
    AlertSubscription,
    AlertTrigger,
    Area,
    AreaLevel,
    ContactField,
    ContactListRow,
    CoverageCell,
    CoverageLabel,
    CoverageStatus,
    DomainContext,
    ExternalContext,
    IndicatorCell,
    IndicatorSnapshot,
    MeetingPointLocation,
    NeedCategory,
    NeedState,
    Permission,
    PermissionPurpose,
    PrivacyProfile,
    ProviderOrganization,
    Report,
    ReporterContact,
    Role,
    Schedule,
    ShareEvent,
    VettingStatus,
    Visibility,
)

ACTIVITY_UNCONFIRMED_AFTER = timedelta(days=7)

# ---------------------------------------------------------------------------
# Vetting (DOM-050)
# ---------------------------------------------------------------------------

VETTING_TRANSITIONS: frozenset[tuple[VettingStatus, VettingStatus]] = frozenset(
    {
        (VettingStatus.unvetted, VettingStatus.vetted),
        (VettingStatus.unvetted, VettingStatus.suspended),
        (VettingStatus.vetted, VettingStatus.suspended),
        (VettingStatus.suspended, VettingStatus.vetted),
    }
)


@dataclass(frozen=True)
class VettingChange:
    provider: ProviderOrganization
    from_status: VettingStatus
    to_status: VettingStatus
    reason: str
    actor_id: str
    at: datetime
    revoke_access: bool  # revoke contact-list access and API keys immediately


def change_vetting(
    ctx: DomainContext, provider: ProviderOrganization, to: VettingStatus, reason: str, now: datetime
) -> VettingChange:
    if not ctx.has(Role.org_admin):
        raise Forbidden("only an org admin can change provider vetting")
    if provider.org_id != ctx.org_id:
        raise Forbidden("provider belongs to another org")
    if not reason or not reason.strip():
        raise ValidationFailed("a reason is required to change vetting")
    if (provider.vetting, to) not in VETTING_TRANSITIONS:
        raise InvalidTransition("provider_vetting", provider.vetting.value, to.value)
    return VettingChange(
        provider=replace(provider, vetting=to, version=provider.version + 1),
        from_status=provider.vetting,
        to_status=to,
        reason=reason.strip(),
        actor_id=ctx.actor_id,
        at=now,
        revoke_access=to is VettingStatus.suspended,
    )


# ---------------------------------------------------------------------------
# Activities (DOM-051/053)
# ---------------------------------------------------------------------------

ACTIVITY_TRANSITIONS: frozenset[tuple[ActivityStatus, ActivityStatus]] = frozenset(
    {
        (ActivityStatus.planned, ActivityStatus.active),
        (ActivityStatus.planned, ActivityStatus.ended),
        (ActivityStatus.active, ActivityStatus.paused),
        (ActivityStatus.active, ActivityStatus.ended),
        (ActivityStatus.paused, ActivityStatus.active),
        (ActivityStatus.paused, ActivityStatus.ended),
    }
)


def log_activity(
    ctx: DomainContext,
    provider: ProviderOrganization,
    activity_id: str,
    *,
    type: ActivityType,
    category: NeedCategory,
    area_ids: frozenset[str],
    schedule: Schedule,
    now: datetime,
    status: ActivityStatus = ActivityStatus.planned,
    visibility: Visibility = Visibility.tenant,
    capacity=None,
    public_location_id: Optional[str] = None,
) -> Activity:
    if ctx.provider_org_id != provider.id or provider.org_id != ctx.org_id:
        raise Forbidden("activity must be logged by the provider's own users")
    if provider.vetting is VettingStatus.suspended:
        raise Forbidden("suspended provider")
    if not area_ids:
        raise ValidationFailed("an activity serves at least one area")
    if schedule.starts_at and schedule.ends_at and schedule.starts_at > schedule.ends_at:
        raise ValidationFailed("schedule start must be <= end")
    return Activity(
        id=activity_id,
        provider_id=provider.id,
        type=type,
        category=category,
        area_ids=area_ids,
        schedule=schedule,
        status=status,
        last_confirmed_at=now,
        visibility=visibility,
        capacity=capacity,
        public_location_id=public_location_id,
    )


def transition_activity(activity: Activity, to: ActivityStatus, now: datetime) -> Activity:
    if (activity.status, to) not in ACTIVITY_TRANSITIONS:
        raise InvalidTransition("activity", activity.status.value, to.value)
    return replace(activity, status=to, last_confirmed_at=now, version=activity.version + 1)


def confirm_activity(activity: Activity, now: datetime) -> Activity:
    if activity.status is ActivityStatus.ended:
        raise InvalidTransition("activity", "ended", "ended", "ended activities are not confirmed")
    return replace(activity, last_confirmed_at=now, version=activity.version + 1)


def display_status(activity: Activity, now: datetime) -> ActivityDisplayStatus:
    if activity.status is not ActivityStatus.ended and now - activity.last_confirmed_at >= ACTIVITY_UNCONFIRMED_AFTER:
        return ActivityDisplayStatus.unconfirmed
    return ActivityDisplayStatus(activity.status.value)


@dataclass(frozen=True)
class ActivityView:
    activity_id: str
    provider_name: Optional[str]
    type: Optional[ActivityType]
    category: NeedCategory
    area_ids: frozenset[str]
    schedule_description: Optional[str]
    status: ActivityDisplayStatus
    details_hidden: bool


def activity_view(
    activity: Activity, provider_name: str, viewer_provider_id: Optional[str], now: datetime
) -> ActivityView:
    """DOM-053: all tenant providers see entries; internal-only hides details from
    other providers but still counts toward coverage."""
    hidden = activity.visibility is Visibility.internal_only and viewer_provider_id != activity.provider_id
    return ActivityView(
        activity_id=activity.id,
        provider_name=None if hidden else provider_name,
        type=None if hidden else activity.type,
        category=activity.category,
        area_ids=activity.area_ids,
        schedule_description=None if hidden else activity.schedule.description,
        status=display_status(activity, now),
        details_hidden=hidden,
    )


# ---------------------------------------------------------------------------
# Coverage (DOM-052)
# ---------------------------------------------------------------------------


def activity_serves(activity: Activity, area_id: str, areas: Mapping[str, Area]) -> bool:
    return any(within(area_id, a, areas) or within(a, area_id, areas) for a in activity.area_ids)


def compute_coverage(
    cells: Iterable[IndicatorCell],
    activities: Iterable[Activity],
    areas: Mapping[str, Area],
    now: datetime,
    threshold: int = 0,
    count_unconfirmed: bool = False,
) -> list[CoverageCell]:
    """Area × category coverage from need cells.

    - ``covered``: an ``active`` activity of that category serves the area
      (unconfirmed activities count only when ``count_unconfirmed``).
    - ``uncovered``: reported active needs above ``threshold`` and no such activity.
    - ``unknown``: no reports, a suppressed cell, or need at/below the threshold.
    """
    acts = [
        a
        for a in activities
        if a.status is ActivityStatus.active
        and (count_unconfirmed or display_status(a, now) is not ActivityDisplayStatus.unconfirmed)
    ]
    out: list[CoverageCell] = []
    for c in cells:
        if not isinstance(c.subject, NeedCategory):
            continue
        serving = tuple(sorted(a.id for a in acts if a.category is c.subject and activity_serves(a, c.area_id, areas)))
        if serving:
            status, reason = CoverageStatus.covered, "active_activity"
        elif c.coverage is CoverageLabel.none:
            status, reason = CoverageStatus.unknown, "no_reports"
        elif c.suppressed:
            status, reason = CoverageStatus.unknown, "suppressed"
        elif (c.active_needs or 0) > threshold:
            status, reason = CoverageStatus.uncovered, "active_need_without_activity"
        else:
            status, reason = CoverageStatus.unknown, "need_at_or_below_threshold"
        out.append(CoverageCell(c.area_id, c.subject, status, serving, reason))
    return out


# ---------------------------------------------------------------------------
# Contact list (DOM-054)
# ---------------------------------------------------------------------------


def _has_permission(perms: Iterable[Permission], key: str, purpose: PermissionPurpose, now: datetime) -> bool:
    return any(p.reporter_key == key and p.purpose is purpose and p.active_at(now) for p in perms)


def in_scope(provider: ProviderOrganization, area_id: str, category: NeedCategory, areas: Mapping[str, Area]) -> bool:
    return category in provider.scope_categories and any(
        within(area_id, s, areas) for s in provider.scope_area_ids
    )


def select_contact_list(
    ctx: DomainContext,
    provider: ProviderOrganization,
    profile: PrivacyProfile,
    reports: Iterable[Report],
    contacts: Mapping[str, ReporterContact],
    permissions: Iterable[Permission],
    areas: Mapping[str, Area],
    now: datetime,
) -> tuple[list[ContactListRow], list[ShareEvent]]:
    """Rows for a vetted provider, and one share event per row returned.

    A reporter appears only when: list consent is active, they have an ``active``
    need in the provider's scope, and the profile enables contact lists. Fields
    follow ``profile.contact_list_fields``.
    """
    if ctx.provider_org_id != provider.id or provider.org_id != ctx.org_id or profile.org_id != ctx.org_id:
        raise Forbidden("contact list is only for the provider's own users")
    if provider.vetting is not VettingStatus.vetted:
        raise Forbidden("contact list requires a vetted provider")
    if not profile.contact_list_enabled:
        raise Forbidden("contact lists are disabled by the privacy profile")
    perms = list(permissions)
    fields = profile.contact_list_fields
    best: dict[tuple[str, NeedCategory], tuple[Report, object]] = {}
    for r in reports:
        if r.org_id != ctx.org_id or not is_aggregatable(r) or r.reporter_key is None:
            continue
        if not _has_permission(perms, r.reporter_key, PermissionPurpose.contact_list, now):
            continue
        if r.reporter_key not in contacts:
            continue
        for n in r.needs:
            if n.state is not NeedState.active or n.replaced_by_id is not None:
                continue
            if not in_scope(provider, r.area_id, n.category, areas):
                continue
            key = (r.reporter_key, n.category)
            cur = best.get(key)
            if cur is None or (r.confirmed_at or r.submitted_at) > (cur[0].confirmed_at or cur[0].submitted_at):
                best[key] = (r, n)
    rows: list[ContactListRow] = []
    events: list[ShareEvent] = []
    for (key, _cat), (r, n) in sorted(best.items(), key=lambda kv: (kv[0][0], kv[0][1].value)):
        c = contacts[key]
        mp = r.location.meeting_point_id if isinstance(r.location, MeetingPointLocation) else None
        rows.append(
            ContactListRow(
                profile_kind=profile.kind,
                reporter_key=key,
                need_id=n.id,  # type: ignore[union-attr]
                category=n.category,  # type: ignore[union-attr]
                urgency=n.stated_urgency,  # type: ignore[union-attr]
                preferred_times=n.preferred_times,  # type: ignore[union-attr]
                phone_encrypted=c.phone_encrypted if ContactField.phone in fields else None,
                alias=c.alias if ContactField.alias in fields else None,
                sector_id=ancestor_at_level(r.area_id, AreaLevel.sector, areas)
                if ContactField.sector in fields
                else None,
                meeting_point_id=mp if ContactField.meeting_point in fields else None,
                name_encrypted=c.name_encrypted if ContactField.name in fields and profile.names_allowed else None,
                address_encrypted=c.address_encrypted if ContactField.address in fields else None,
            )
        )
        events.append(ShareEvent(provider.id, ctx.actor_id, key, n.id, now))  # type: ignore[union-attr]
    return rows, events


# ---------------------------------------------------------------------------
# Alerts (DOM-055)
# ---------------------------------------------------------------------------


def dedup_key(sub: AlertSubscription, area_id: str) -> str:
    return f"{sub.id}|{sub.trigger.value}|{area_id}"


def evaluate_alerts(
    subscriptions: Iterable[AlertSubscription],
    providers: Mapping[str, ProviderOrganization],
    snapshot: IndicatorSnapshot,
    previous: Optional[IndicatorSnapshot],
    coverage: Sequence[CoverageCell],
    external: Iterable[ExternalContext],
    last_fired: Mapping[str, datetime],
    now: datetime,
    areas: Mapping[str, Area],
) -> list[Alert]:
    """Aggregate-only, suppression-respecting alerts, deduplicated per subscription
    per area per window. Suppressed or unknown cells never trigger."""
    cells = {(c.area_id, c.subject): c for c in snapshot.cells}
    prev = {(c.area_id, c.subject): c for c in previous.cells} if previous else {}
    cov = {(c.area_id, c.category): c for c in coverage}
    ext = list(external)
    fired = dict(last_fired)
    out: list[Alert] = []
    for sub in subscriptions:
        prov = providers.get(sub.provider_id)
        if not sub.active or prov is None or prov.vetting is VettingStatus.suspended:
            continue
        for area_id in sorted(sub.area_ids):
            key = dedup_key(sub, area_id)
            last = fired.get(key)
            if last is not None and now - last < sub.dedup_window:
                continue
            cell = cells.get((area_id, sub.category))
            usable = cell is not None and not cell.suppressed and cell.coverage is CoverageLabel.reported
            value: Optional[int] = None
            source: Optional[str] = None
            hit = False
            if sub.trigger is AlertTrigger.new_urgent_needs and usable:
                p = prev.get((area_id, sub.category))
                before = p.urgent_active_needs if p and not p.suppressed and p.urgent_active_needs else 0
                value = cell.urgent_active_needs or 0
                hit = value > before
            elif sub.trigger is AlertTrigger.active_needs_above and usable:
                value = cell.active_needs or 0
                hit = sub.threshold is not None and value > sub.threshold
            elif sub.trigger is AlertTrigger.area_uncovered:
                cc = cov.get((area_id, sub.category))
                hit = cc is not None and cc.status is CoverageStatus.uncovered
            elif sub.trigger is AlertTrigger.external_outage:
                service = RELATED_SERVICE[sub.category]
                sig = [
                    e
                    for e in ext
                    if e.large_outage and e.service is service
                    and (within(area_id, e.area_id, areas) or within(e.area_id, area_id, areas))
                ]
                if sig:
                    hit, source = True, max(sig, key=lambda e: e.observed_at).source
            if not hit:
                continue
            fired[key] = now
            out.append(
                Alert(
                    subscription_id=sub.id,
                    trigger=sub.trigger,
                    area_id=area_id,
                    category=sub.category,
                    bucket=snapshot.bucket if cell is not None else None,
                    value=value,
                    coverage=cell.coverage if cell is not None else None,
                    method_version=snapshot.method_version,
                    source=source,
                    created_at=now,
                    dedup_key=key,
                )
            )
    return out
