"""Public dashboard (DOM-080/081, SEC-17).

Public cells are derived from indicator snapshots using the profile's public
level, k, and delay; only banded need counts, status mix, coverage, and freshness
are published. Public models are separate types (CON-016).
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping, Optional, Sequence

from app.domain.types import (
    Activity,
    ActivityStatus,
    CoverageLabel,
    IndicatorCell,
    IndicatorSnapshot,
    NeedCategory,
    PrivacyProfile,
    ProviderOrganization,
    PublicActivity,
    PublicIndicatorCell,
    ServiceStatus,
    VettingStatus,
    Visibility,
)

BANDS: tuple[tuple[int, Optional[int]], ...] = ((1, 4), (5, 9), (10, 24), (25, 49), (50, 99), (100, None))


def band(n: int) -> str:
    if n <= 0:
        return "0"
    for lo, hi in BANDS:
        if hi is None or n <= hi:
            if hi is None:
                return f"{lo}+"
            return f"{lo}–{hi}"
    raise AssertionError("unreachable")


def publishable(snapshot: IndicatorSnapshot, profile: PrivacyProfile, now: datetime) -> bool:
    return profile.public_dashboard_enabled and snapshot.bucket_end <= now - profile.public_delay


def public_cell(cell: IndicatorCell, k: int) -> PublicIndicatorCell:
    units = cell.distinct_households if cell.distinct_households is not None else cell.distinct_reporters
    hidden = cell.suppressed or cell.coverage is not CoverageLabel.reported or units is None or units < k
    coverage = cell.coverage
    if hidden and coverage is CoverageLabel.reported:
        coverage = CoverageLabel.thin  # below the public k
    need_band = None
    status_bands = None
    if not hidden:
        if isinstance(cell.subject, NeedCategory) and cell.active_needs is not None:
            need_band = band(cell.active_needs)
        if cell.status_mix is not None:
            status_bands = {ServiceStatus(s): band(n) for s, n in cell.status_mix.items()}
    return PublicIndicatorCell(
        area_id=cell.area_id,
        level=cell.level,
        subject=cell.subject,
        bucket=cell.bucket,
        bucket_end=cell.bucket_end,
        coverage=coverage,
        need_count_band=need_band,
        status_mix_bands=status_bands,
        freshness=None if hidden else cell.freshness,
    )


def public_cells(snapshot: IndicatorSnapshot, profile: PrivacyProfile, now: datetime) -> list[PublicIndicatorCell]:
    """Only cells at the profile's public level, after the delay, with public k."""
    if not publishable(snapshot, profile, now) or snapshot.org_id != profile.org_id:
        return []
    return [public_cell(c, profile.public_k) for c in snapshot.cells if c.level is profile.public_level]


def public_activities(
    activities: Iterable[Activity], providers: Mapping[str, ProviderOrganization], profile: PrivacyProfile
) -> list[PublicActivity]:
    """DOM-081: only activities a provider marked public."""
    if not profile.public_dashboard_enabled:
        return []
    out = []
    for a in activities:
        p = providers.get(a.provider_id)
        if a.visibility is not Visibility.public or p is None or p.vetting is VettingStatus.suspended:
            continue
        if a.status not in (ActivityStatus.planned, ActivityStatus.active):
            continue
        out.append(PublicActivity(p.name, a.type, a.area_ids, a.schedule.description, a.public_location_id))
    return out
