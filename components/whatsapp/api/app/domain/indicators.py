"""Area indicators (DOM-040..046).

``compute_snapshot`` builds one cell per area (sector and parish) × subject (need
category or service) × bucket. Rules, all declared in ``IndicatorMethod``:

- Inclusion: ``reports.is_aggregatable`` only, with ``confirmed_at`` in the bucket.
- Repeat reporters count once: per reporter key and subject, the reporter's latest
  report in the bucket is their current state (DOM-014).
- Unknown is never zero: a cell with no reports has coverage ``none`` and ``None``
  counts (DOM-041).
- Suppression (DOM-044 / SEC-10): a cell under k distinct units is suppressed (all
  counts ``None``) and its data merges up into the parent area's cell, which is
  computed over all of its sectors. If exactly one sibling under a reported parent
  is suppressed, the next-smallest sibling is suppressed too, so the hidden value
  cannot be recovered by subtraction.
- External context is a separate layer (DOM-045): it only affects confidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Iterable, Mapping, Optional, Sequence

from app.domain.reports import is_aggregatable, report_watermark
from app.domain.types import (
    Area,
    AreaLevel,
    AreaOfNeed,
    Bucket,
    Confidence,
    ConfidenceLabel,
    CoverageLabel,
    ExternalAgreement,
    ExternalContext,
    IndicatorCell,
    IndicatorSnapshot,
    Need,
    NeedCategory,
    NeedState,
    PrivacyProfile,
    RemainingSupply,
    Report,
    Service,
    ServiceStatus,
    Subject,
    Urgency,
)

DEFAULT_RANKING_CRITERIA: tuple[str, ...] = (
    "urgent_active_needs_desc",
    "active_needs_per_reporter_desc",
    "oldest_active_need_age_desc",
    "freshness_desc",
)

RELATED_SERVICE: dict[NeedCategory, Service] = {
    NeedCategory.water_drinking: Service.piped_water,
    NeedCategory.water_other: Service.piped_water,
    NeedCategory.charging: Service.electricity,
}

ALL_SUBJECTS: tuple[Subject, ...] = tuple(NeedCategory) + tuple(Service)


@dataclass(frozen=True)
class IndicatorMethod:
    version: str = "indicators-1"
    cell_levels: tuple[AreaLevel, ...] = (AreaLevel.sector, AreaLevel.parish)
    fresh_within: timedelta = timedelta(hours=6)
    stale_after: timedelta = timedelta(hours=24)
    mostly_unreviewed_share: float = 0.5
    ranking_criteria: tuple[str, ...] = DEFAULT_RANKING_CRITERIA


DEFAULT_METHOD = IndicatorMethod()


# ---------------------------------------------------------------------------
# Area helpers
# ---------------------------------------------------------------------------


def ancestors(area_id: str, areas: Mapping[str, Area]) -> list[str]:
    out: list[str] = []
    seen = {area_id}
    cur = areas.get(area_id)
    while cur is not None and cur.parent_id is not None and cur.parent_id not in seen:
        out.append(cur.parent_id)
        seen.add(cur.parent_id)
        cur = areas.get(cur.parent_id)
    return out


def within(area_id: str, scope_area_id: str, areas: Mapping[str, Area]) -> bool:
    return area_id == scope_area_id or scope_area_id in ancestors(area_id, areas)


def ancestor_at_level(area_id: str, level: AreaLevel, areas: Mapping[str, Area]) -> Optional[str]:
    for a in [area_id, *ancestors(area_id, areas)]:
        if a in areas and areas[a].level is level:
            return a
    return None


# ---------------------------------------------------------------------------
# Cell computation
# ---------------------------------------------------------------------------


def reporter_identity(report: Report) -> str:
    """Distinct-source unit. Reports without a key are their own source."""
    return report.reporter_key or f"anon:{report.id}"


def _unit_identity(report: Report, households: bool) -> str:
    if households and report.household_ref is not None:
        return f"hh:{report.household_ref}"
    return reporter_identity(report)


def _order_key(r: Report):
    return (r.confirmed_at or r.submitted_at, r.id)


@dataclass
class _Inputs:
    reports: list[Report]
    needs: list[Need]  # latest per reporter for this category, any state
    statuses: list[ServiceStatus]  # latest per reporter for this service
    freshness: Optional[datetime]


def _collect(subject: Subject, reports: Sequence[Report]) -> _Inputs:
    latest_by_reporter: dict[str, tuple[Report, object]] = {}
    for r in sorted(reports, key=_order_key):
        if isinstance(subject, NeedCategory):
            items = [n for n in r.needs if n.category is subject]
        else:
            items = sorted((o for o in r.observations if o.service is subject), key=lambda o: o.observed_at)
        if not items:
            continue
        latest_by_reporter[reporter_identity(r)] = (r, items[-1])
    included = [r for r, _ in latest_by_reporter.values()]
    # Reports that mention the subject but are not the reporter's latest still
    # count as reviewed/unreviewed inputs for the confidence share.
    contributing = [
        r
        for r in reports
        if (isinstance(subject, NeedCategory) and any(n.category is subject for n in r.needs))
        or (isinstance(subject, Service) and any(o.service is subject for o in r.observations))
    ]
    needs: list[Need] = []
    statuses: list[ServiceStatus] = []
    fresh: Optional[datetime] = None
    for r, item in latest_by_reporter.values():
        if isinstance(subject, NeedCategory):
            needs.append(item)  # type: ignore[arg-type]
            t = r.confirmed_at
        else:
            statuses.append(item.status)  # type: ignore[union-attr]
            t = item.observed_at  # type: ignore[union-attr]
        if t is not None and (fresh is None or t > fresh):
            fresh = t
    return _Inputs(reports=contributing or included, needs=needs, statuses=statuses, freshness=fresh)


def coverage_label(units: int, k: int) -> CoverageLabel:
    if units == 0:
        return CoverageLabel.none
    if units < k:
        return CoverageLabel.thin
    return CoverageLabel.reported


def _majority_status(statuses: Iterable[ServiceStatus]) -> Optional[ServiceStatus]:
    c = Counter(s for s in statuses if s is not ServiceStatus.unknown)
    if not c:
        return None
    return c.most_common(1)[0][0]


def external_agreement(
    subject: Subject,
    area_id: str,
    statuses: Sequence[ServiceStatus],
    has_active_need: bool,
    external: Iterable[ExternalContext],
    areas: Mapping[str, Area],
) -> tuple[ExternalAgreement, Optional[str]]:
    service = subject if isinstance(subject, Service) else RELATED_SERVICE[subject]
    relevant = [
        e
        for e in external
        if e.service is service and (within(area_id, e.area_id, areas) or within(e.area_id, area_id, areas))
    ]
    if not relevant:
        return ExternalAgreement.no_data, None
    latest = max(relevant, key=lambda e: e.observed_at)
    ext_out = latest.status in (ServiceStatus.unavailable, ServiceStatus.intermittent)
    if latest.status is ServiceStatus.unknown:
        return ExternalAgreement.no_data, latest.source
    if isinstance(subject, Service):
        maj = _majority_status(statuses)
        if maj is None:
            return ExternalAgreement.no_data, latest.source
        rep_out = maj in (ServiceStatus.unavailable, ServiceStatus.intermittent)
        return (ExternalAgreement.agrees if rep_out == ext_out else ExternalAgreement.disagrees), latest.source
    if not has_active_need:
        return ExternalAgreement.no_data, latest.source
    return (ExternalAgreement.agrees if ext_out else ExternalAgreement.disagrees), latest.source


def confidence_for(
    *,
    units: int,
    k: int,
    pending_share: Optional[float],
    freshness: Optional[datetime],
    now: datetime,
    agreement: ExternalAgreement,
    external_source: Optional[str],
    method: IndicatorMethod = DEFAULT_METHOD,
) -> Confidence:
    """DOM-042: a transparent label with stated reasons, not a truth score.

    Rule (method ``indicators-1``):
      - no reports or fewer than k independent sources → low
      - otherwise count concerns (mostly unreviewed, stale, external disagreement):
        0 concerns and >= 2k sources → high; >= 2 concerns → low; else medium.
    """
    reasons: list[str] = []
    if units == 0:
        return Confidence(ConfidenceLabel.low, ("no_reports",))
    concerns = 0
    if units < k:
        reasons.append("few_independent_sources")
    elif units >= 2 * k:
        reasons.append("multiple_independent_sources")
    else:
        reasons.append("some_independent_sources")
    if pending_share is not None and pending_share > method.mostly_unreviewed_share:
        reasons.append("mostly_unreviewed")
        concerns += 1
    elif pending_share:
        reasons.append("some_unreviewed")
    if freshness is not None:
        age = now - freshness
        if age > method.stale_after:
            reasons.append("stale_data")
            concerns += 1
        elif age <= method.fresh_within:
            reasons.append("fresh_data")
    if agreement is ExternalAgreement.agrees:
        reasons.append(f"external_agrees:{external_source}")
    elif agreement is ExternalAgreement.disagrees:
        reasons.append(f"external_disagrees:{external_source}")
        concerns += 1
    if units < k:
        label = ConfidenceLabel.low
    elif concerns == 0 and units >= 2 * k:
        label = ConfidenceLabel.high
    elif concerns >= 2:
        label = ConfidenceLabel.low
    else:
        label = ConfidenceLabel.medium
    return Confidence(label, tuple(reasons))


def _cell(
    area: Area,
    subject: Subject,
    bucket: Bucket,
    start: datetime,
    end: datetime,
    reports: Sequence[Report],
    profile: PrivacyProfile,
    now: datetime,
    external: Sequence[ExternalContext],
    areas: Mapping[str, Area],
    method: IndicatorMethod,
) -> IndicatorCell:
    households = profile.household_records_allowed
    data = _collect(subject, reports)
    included = data.reports
    latest_reports = {reporter_identity(r) for r in included}
    reporters = len(latest_reports)
    hh_count = len({_unit_identity(r, True) for r in included}) if households else None
    units = hh_count if households and hh_count is not None else reporters
    coverage = coverage_label(units, profile.aggregate_k)
    unit_label = "hogares" if households else "reportantes"
    watermark = max((report_watermark(r) for r in included), default=None)
    is_need = isinstance(subject, NeedCategory)
    active = [n for n in data.needs if n.state is NeedState.active and n.replaced_by_id is None]
    pending_share = (sum(1 for r in included if r.pending_review) / len(included)) if included else None
    agreement, ext_src = external_agreement(subject, area.id, data.statuses, bool(active), external, areas)
    conf = confidence_for(
        units=units,
        k=profile.aggregate_k,
        pending_share=pending_share,
        freshness=data.freshness,
        now=now,
        agreement=agreement,
        external_source=ext_src,
        method=method,
    )
    base = dict(
        area_id=area.id,
        level=area.level,
        subject=subject,
        bucket=bucket,
        bucket_start=start,
        bucket_end=end,
        coverage=coverage,
        confidence=conf,
        unit_label=unit_label,
        method_version=method.version,
        input_watermark=watermark,
    )
    if coverage is CoverageLabel.none:
        return IndicatorCell(**base, **_EMPTY_COUNTS, suppressed=False, merged_into_area_id=None)
    if coverage is CoverageLabel.thin:
        return IndicatorCell(
            **{**base, "input_watermark": None},
            **_EMPTY_COUNTS,
            suppressed=True,
            merged_into_area_id=area.parent_id,
        )
    return IndicatorCell(
        **base,
        suppressed=False,
        merged_into_area_id=None,
        active_needs=len(active) if is_need else None,
        urgent_active_needs=sum(1 for n in active if n.stated_urgency is Urgency.urgent) if is_need else None,
        distinct_reporters=reporters,
        distinct_households=hh_count,
        people_affected_known=sum(n.people_affected for n in active if n.people_affected is not None)
        if is_need
        else None,
        people_affected_unknown_count=sum(1 for n in active if n.people_affected is None) if is_need else None,
        urgency_mix=dict(Counter(n.stated_urgency for n in active)) if is_need else None,
        supply_mix=dict(Counter(n.remaining_supply for n in active)) if is_need else None,
        status_mix=None if is_need else dict(Counter(data.statuses)),
        freshness=data.freshness,
        oldest_active_need_at=min((n.created_at for n in active), default=None) if is_need else None,
        pending_review_share=pending_share,
    )


_EMPTY_COUNTS = dict(
    active_needs=None,
    urgent_active_needs=None,
    distinct_reporters=None,
    distinct_households=None,
    people_affected_known=None,
    people_affected_unknown_count=None,
    urgency_mix=None,
    supply_mix=None,
    status_mix=None,
    freshness=None,
    oldest_active_need_at=None,
    pending_review_share=None,
)


def _secondary_suppression(cells: list[IndicatorCell], areas: Mapping[str, Area]) -> list[IndicatorCell]:
    by_key: dict[tuple, list[int]] = {}
    for i, c in enumerate(cells):
        parent = areas[c.area_id].parent_id
        if parent is not None:
            by_key.setdefault((parent, c.subject), []).append(i)
    out = list(cells)
    index = {(c.area_id, c.subject): i for i, c in enumerate(cells)}
    for (parent, subject), idxs in by_key.items():
        pi = index.get((parent, subject))
        if pi is None or out[pi].suppressed or out[pi].coverage is not CoverageLabel.reported:
            continue
        suppressed = [i for i in idxs if out[i].suppressed]
        visible = [i for i in idxs if not out[i].suppressed and out[i].coverage is CoverageLabel.reported]
        if len(suppressed) == 1 and visible:
            j = min(visible, key=lambda i: (out[i].distinct_reporters or 0, out[i].area_id))
            c = out[j]
            out[j] = replace(
                c,
                **_EMPTY_COUNTS,
                input_watermark=None,
                suppressed=True,
                merged_into_area_id=parent,
                confidence=Confidence(c.confidence.label, c.confidence.reasons + ("secondary_suppression",)),
            )
    return out


def compute_snapshot(
    org_id: str,
    reports: Iterable[Report],
    areas: Mapping[str, Area],
    profile: PrivacyProfile,
    bucket: Bucket,
    bucket_end: datetime,
    now: datetime,
    external: Iterable[ExternalContext] = (),
    method: IndicatorMethod = DEFAULT_METHOD,
    subjects: Sequence[Subject] = ALL_SUBJECTS,
) -> IndicatorSnapshot:
    start = bucket_end - bucket.duration
    in_window = [
        r
        for r in reports
        if r.org_id == org_id
        and is_aggregatable(r)
        and r.confirmed_at is not None
        and start <= r.confirmed_at < bucket_end
    ]
    ext = [e for e in external if start - method.stale_after <= e.observed_at < bucket_end]
    cell_areas = [a for a in areas.values() if a.level in method.cell_levels]
    by_area: dict[str, list[Report]] = {a.id: [] for a in cell_areas}
    for r in in_window:
        for a in [r.area_id, *ancestors(r.area_id, areas)]:
            if a in by_area:
                by_area[a].append(r)
    cells = [
        _cell(a, s, bucket, start, bucket_end, by_area[a.id], profile, now, ext, areas, method)
        for a in sorted(cell_areas, key=lambda a: a.id)
        for s in subjects
    ]
    cells = _secondary_suppression(cells, areas)
    watermark = max((report_watermark(r) for r in in_window), default=None)
    return IndicatorSnapshot(
        org_id=org_id,
        bucket=bucket,
        bucket_end=bucket_end,
        method_version=method.version,
        profile_version=profile.version,
        input_watermark=watermark,
        computed_at=now,
        cells=tuple(cells),
    )


# ---------------------------------------------------------------------------
# Ranking (DOM-043)
# ---------------------------------------------------------------------------


def _rank_key(c: IndicatorCell):
    per_reporter = Fraction(c.active_needs or 0, c.distinct_reporters or 1)
    oldest = c.oldest_active_need_at.timestamp() if c.oldest_active_need_at else float("inf")
    fresh = -(c.freshness.timestamp()) if c.freshness else float("inf")
    return (-(c.urgent_active_needs or 0), -per_reporter, oldest, fresh, c.area_id, str(c.subject))


def rank_areas(cells: Iterable[IndicatorCell], method: IndicatorMethod = DEFAULT_METHOD) -> list[AreaOfNeed]:
    """Areas of greatest need, by the declared criteria only (no hidden weights).

    Only unsuppressed ``reported`` need cells with at least one active need are
    ranked; unknown areas are not ranked as "no need". Ties break by area id.
    """
    if method.ranking_criteria != DEFAULT_RANKING_CRITERIA:
        raise ValueError("only the declared default criteria are implemented")
    ranked = sorted(
        (
            c
            for c in cells
            if isinstance(c.subject, NeedCategory)
            and not c.suppressed
            and c.coverage is CoverageLabel.reported
            and (c.active_needs or 0) > 0
        ),
        key=_rank_key,
    )
    return [
        AreaOfNeed(cell=c, rank=i + 1, criteria=method.ranking_criteria, method_version=method.version)
        for i, c in enumerate(ranked)
    ]

