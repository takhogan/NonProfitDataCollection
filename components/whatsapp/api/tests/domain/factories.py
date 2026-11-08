"""Builders for domain tests. Pure data; no database."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from app.domain.profiles import protective_profile, standard_profile
from app.domain.types import (
    Area,
    AreaLevel,
    Channel,
    Disposition,
    DomainContext,
    MeetingPointLocation,
    Need,
    NeedCategory,
    NeedState,
    Observation,
    PermissionPurpose,
    Relationship,
    RemainingSupply,
    Report,
    ReportState,
    Role,
    Service,
    ServiceStatus,
    TimePrecision,
    Urgency,
)

ORG = "org_csl"
OTHER_ORG = "org_other"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

AREAS: dict[str, Area] = {
    a.id: a
    for a in [
        Area("mun", AreaLevel.municipality, "Libertador"),
        Area("P1", AreaLevel.parish, "Parroquia 1", "mun"),
        Area("P2", AreaLevel.parish, "Parroquia 2", "mun"),
        Area("S1", AreaLevel.sector, "Sector 1", "P1"),
        Area("S2", AreaLevel.sector, "Sector 2", "P1"),
        Area("S3", AreaLevel.sector, "Sector 3", "P1"),
        Area("S4", AreaLevel.sector, "Sector 4", "P2"),
    ]
}


def ctx(*roles: Role, org: str = ORG, actor: str = "user_1", provider: Optional[str] = None) -> DomainContext:
    return DomainContext(org, actor, frozenset(roles or {Role.coordinator}), provider_org_id=provider)


def protective(**kw):
    return replace(protective_profile(ORG), **kw)


def standard(**kw):
    return replace(standard_profile(ORG), **kw)


_n = [0]


def _next(prefix: str) -> str:
    _n[0] += 1
    return f"{prefix}{_n[0]}"


def need(
    category: NeedCategory = NeedCategory.water_drinking,
    *,
    state: NeedState = NeedState.active,
    urgency: Urgency = Urgency.unknown,
    supply: RemainingSupply = RemainingSupply.unknown,
    people: Optional[int] = None,
    at: datetime = T0,
    report_id: str = "",
    id: Optional[str] = None,
    **kw,
) -> Need:
    return Need(
        id=id or _next("need"),
        report_id=report_id,
        category=category,
        state=state,
        stated_urgency=urgency,
        remaining_supply=supply,
        created_at=at,
        last_confirmed_at=at,
        people_affected=people,
        state_changed_at=at,
        **kw,
    )


def obs(service: Service, status: ServiceStatus, at: datetime = T0) -> Observation:
    return Observation(_next("obs"), "", service, status, at, TimePrecision.exact, None, TimePrecision.unknown)


def report(
    *,
    id: Optional[str] = None,
    area: str = "S1",
    key: Optional[str] = None,
    at: datetime = T0,
    needs: Sequence[Need] = (),
    observations: Sequence[Observation] = (),
    state: ReportState = ReportState.confirmed,
    org: str = ORG,
    household: Optional[str] = None,
    permissions=frozenset({PermissionPurpose.notice_ack}),
    disposition: Optional[Disposition] = None,
    meeting_point: Optional[str] = None,
    **kw,
) -> Report:
    rid = id or _next("rep")
    return Report(
        id=rid,
        org_id=org,
        channel=Channel.whatsapp,
        relationship=Relationship.self,
        area_id=area,
        state=state,
        profile_version=1,
        notice_version="n1",
        questionnaire_version="q1",
        submitted_at=at,
        reporter_key=key,
        confirmed_at=at if state in (ReportState.confirmed, ReportState.superseded) else None,
        location=MeetingPointLocation(meeting_point_id=meeting_point) if meeting_point else None,
        observations=tuple(replace(o, report_id=rid) for o in observations),
        needs=tuple(replace(n, report_id=rid) for n in needs),
        permissions=permissions,
        household_ref=household,
        disposition=disposition,
        **kw,
    )


def reporters_in(area: str, n: int, *, at: datetime = T0, category=NeedCategory.water_drinking, prefix="k", **need_kw):
    """n distinct reporters each with one need of ``category`` in ``area``."""
    return [
        report(area=area, key=f"{prefix}{area}_{i}", at=at + timedelta(minutes=i), needs=[need(category, at=at, **need_kw)])
        for i in range(n)
    ]
