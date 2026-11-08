"""Data-quality review (DOM-070..074).

Machine rules only *propose* (comparison results, review tasks, pending flags).
Only a human ``duplicate`` or ``spam`` disposition removes a report from
aggregates (DOM-073); everything else keeps counting and only lowers confidence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import combinations
from typing import Iterable, Mapping, Optional, Sequence

from app.domain.errors import Forbidden, InvalidTransition, ValidationFailed
from app.domain.ports import IdGenerator
from app.domain.reports import is_aggregatable
from app.domain.types import (
    ComparisonKind,
    ComparisonResult,
    Disposition,
    DomainContext,
    ExternalContext,
    IndicatorSnapshot,
    Report,
    ReviewDisposition,
    ReviewTask,
    ReviewTaskKind,
    ReviewTaskState,
    Role,
    Service,
    ServiceStatus,
)


@dataclass(frozen=True)
class ComparisonRule:
    version: str = "compare-1"
    overlap: timedelta = timedelta(hours=6)  # observations closer than this overlap
    flood_window: timedelta = timedelta(hours=1)
    flood_threshold: int = 30  # confirmed reports per area per window
    outlier_factor: int = 3


DEFAULT_RULE = ComparisonRule()


# ---------------------------------------------------------------------------
# Comparison (DOM-071)
# ---------------------------------------------------------------------------


def _latest_status(report: Report, service: Service):
    obs = [o for o in report.observations if o.service is service]
    return max(obs, key=lambda o: o.observed_at) if obs else None


def compare(a: Report, b: Report, rule: ComparisonRule = DEFAULT_RULE) -> list[ComparisonResult]:
    """Compare two reports. Only compatible pairs (same org, same area, same
    service, overlapping observation time) are compared. The same reporter changing
    status over time is a ``transition``, never a conflict."""
    if a.id == b.id or a.org_id != b.org_id or a.area_id != b.area_id:
        return []
    if not (is_aggregatable(a) and is_aggregatable(b)):
        return []
    ids = tuple(sorted((a.id, b.id)))
    same_reporter = a.reporter_key is not None and a.reporter_key == b.reporter_key
    out: list[ComparisonResult] = []
    if not same_reporter and a.source_digest is not None and a.source_digest == b.source_digest:
        out.append(ComparisonResult(ComparisonKind.duplicate_candidate, ids, rule.version, ("same_source_digest",)))
    for service in Service:
        oa, ob = _latest_status(a, service), _latest_status(b, service)
        if oa is None or ob is None:
            continue
        if ServiceStatus.unknown in (oa.status, ob.status) or oa.status is ob.status:
            continue
        if same_reporter:
            out.append(
                ComparisonResult(
                    ComparisonKind.transition, ids, rule.version, (f"same_reporter_status_change:{service.value}",)
                )
            )
            continue
        if abs(oa.observed_at - ob.observed_at) > rule.overlap:
            continue
        out.append(
            ComparisonResult(
                ComparisonKind.conflict,
                ids,
                rule.version,
                (f"conflicting_{service.value}:{oa.status.value}/{ob.status.value}", "same_area", "overlapping_time"),
            )
        )
    return out


def find_comparisons(reports: Iterable[Report], rule: ComparisonRule = DEFAULT_RULE) -> list[ComparisonResult]:
    by_area: dict[tuple[str, str], list[Report]] = defaultdict(list)
    for r in reports:
        by_area[(r.org_id, r.area_id)].append(r)
    out: list[ComparisonResult] = []
    for group in by_area.values():
        group.sort(key=lambda r: r.id)
        for a, b in combinations(group, 2):
            out.extend(compare(a, b, rule))
    return out


def tasks_from_comparisons(
    comparisons: Iterable[ComparisonResult], ids: IdGenerator, now: datetime
) -> list[ReviewTask]:
    """Conflicts and duplicate candidates become review tasks; transitions do not."""
    kinds = {
        ComparisonKind.conflict: ReviewTaskKind.conflicting_observation,
        ComparisonKind.duplicate_candidate: ReviewTaskKind.duplicate_candidate,
    }
    return [
        ReviewTask(ids.new_id("rt"), kinds[c.kind], c.report_ids, ReviewTaskState.open, now, c.rule_version, c.reasons)
        for c in comparisons
        if c.kind in kinds
    ]


def mark_pending(reports: Iterable[Report], tasks: Iterable[ReviewTask]) -> list[Report]:
    """Reports in open tasks are pending review: they still count (DOM-073)."""
    pending = {rid for t in tasks if t.state is ReviewTaskState.open for rid in t.report_ids}
    return [replace(r, pending_review=True) if r.id in pending else r for r in reports]


# ---------------------------------------------------------------------------
# Other task sources (DOM-070)
# ---------------------------------------------------------------------------


def flag_urgent(report: Report, ids: IdGenerator, now: datetime) -> tuple[Report, ReviewTask]:
    """D8 / DOM-023: a coordinator may flag; aggregates never re-weight."""
    task = ReviewTask(ids.new_id("rt"), ReviewTaskKind.urgent_flag, (report.id,), ReviewTaskState.open, now,
                      area_id=report.area_id)
    return replace(report, urgent_flagged=True, pending_review=True), task


def detect_floods(
    reports: Iterable[Report], now: datetime, ids: IdGenerator, rule: ComparisonRule = DEFAULT_RULE
) -> list[ReviewTask]:
    """Bursts per area route to review (SEC-11); nothing is excluded."""
    by_area: dict[str, list[str]] = defaultdict(list)
    for r in reports:
        if is_aggregatable(r) and r.confirmed_at is not None and now - r.confirmed_at <= rule.flood_window:
            by_area[r.area_id].append(r.id)
    return [
        ReviewTask(ids.new_id("rt"), ReviewTaskKind.flood, tuple(sorted(rids)), ReviewTaskState.open, now,
                   rule.version, (f"{len(rids)}_reports_in_{rule.flood_window}",), area_id=area)
        for area, rids in sorted(by_area.items())
        if len(rids) >= rule.flood_threshold
    ]


def detect_outlier_cells(
    current: IndicatorSnapshot,
    previous: Optional[IndicatorSnapshot],
    ids: IdGenerator,
    now: datetime,
    k: int,
    rule: ComparisonRule = DEFAULT_RULE,
) -> list[ReviewTask]:
    """A sudden spike in a cell opens an outlier task (SEC-11). Repeat reports are
    already collapsed per reporter, so the spike is measured in active needs: at
    least ``outlier_factor`` times the previous bucket and at least k more. The
    reporter counts are stated in the reasons. Nothing is excluded."""
    if previous is None:
        return []
    prev = {(c.area_id, c.subject): c for c in previous.cells}
    out = []
    for c in current.cells:
        p = prev.get((c.area_id, c.subject))
        if c.suppressed or c.active_needs is None or p is None or p.active_needs is None:
            continue
        if c.active_needs >= rule.outlier_factor * max(p.active_needs, 1) and c.active_needs - p.active_needs >= k:
            out.append(
                ReviewTask(ids.new_id("rt"), ReviewTaskKind.outlier_cell, (), ReviewTaskState.open, now, rule.version,
                           (f"spike_{p.active_needs}_to_{c.active_needs}",
                            f"reporters_{p.distinct_reporters}_to_{c.distinct_reporters}",
                            f"subject:{c.subject.value}"),
                           area_id=c.area_id)
            )
    return out


def evidence_review_tasks(snapshot: IndicatorSnapshot, ids: IdGenerator, now: datetime) -> list[ReviewTask]:
    """DOM-074: external disagreement may open an area-scoped task; it never
    changes report or need state."""
    out = []
    for c in snapshot.cells:
        if c.suppressed:
            continue
        reasons = [r for r in c.confidence.reasons if r.startswith("external_disagrees")]
        if reasons:
            out.append(
                ReviewTask(ids.new_id("rt"), ReviewTaskKind.conflicting_observation, (), ReviewTaskState.open, now,
                           None, tuple(reasons) + (f"subject:{c.subject.value}",), area_id=c.area_id)
            )
    return out


def attach_external_evidence(
    context: ExternalContext, reports: Sequence[Report]
) -> tuple[ExternalContext, Sequence[Report]]:
    """External evidence links at area scope and returns reports untouched."""
    return context, reports


# ---------------------------------------------------------------------------
# Dispositions (DOM-072)
# ---------------------------------------------------------------------------


def resolve_review(
    ctx: DomainContext,
    task: ReviewTask,
    decision: ReviewDisposition,
    reports: Mapping[str, Report],
) -> tuple[ReviewTask, list[Report]]:
    """Apply a human disposition. Returns the resolved task and updated reports."""
    if not (ctx.has(Role.reviewer) or ctx.has(Role.org_admin)):
        raise Forbidden("only reviewers record dispositions")
    if task.state is not ReviewTaskState.open:
        raise InvalidTransition("review_task", task.state.value, ReviewTaskState.resolved.value)
    if decision.task_id != task.id:
        raise ValidationFailed("disposition is for another task")
    if not decision.rationale.strip():
        raise ValidationFailed("a rationale is required")
    if decision.reviewer_id != ctx.actor_id:
        raise Forbidden("reviewer must be the acting user")
    targets = [reports[rid] for rid in task.report_ids if rid in reports]
    if any(r.org_id != ctx.org_id for r in targets):
        raise Forbidden("report belongs to another org")
    d = decision.disposition
    updated: list[Report] = []
    if d is Disposition.duplicate:
        if decision.primary_report_id not in task.report_ids or len(task.report_ids) < 2:
            raise ValidationFailed("duplicate needs a primary report among the task's reports")
        for r in targets:
            if r.id == decision.primary_report_id:
                updated.append(replace(r, disposition=Disposition.valid, pending_review=False))
            else:
                updated.append(replace(r, disposition=Disposition.duplicate,
                                       duplicate_of_id=decision.primary_report_id, pending_review=False))
    elif d is Disposition.spam:
        updated = [replace(r, disposition=Disposition.spam, exclusion_reason=decision.rationale,
                           pending_review=False) for r in targets]
    elif d is Disposition.location_corrected:
        if decision.corrected_area_id is None:
            raise ValidationFailed("location_corrected needs corrected_area_id")
        updated = [replace(r, disposition=Disposition.location_corrected, area_id=decision.corrected_area_id,
                           pending_review=False) for r in targets]
    elif d is Disposition.valid:
        updated = [replace(r, disposition=Disposition.valid, pending_review=False) for r in targets]
    else:  # unresolved: still counts, still lowers confidence
        updated = [replace(r, disposition=Disposition.unresolved, pending_review=True) for r in targets]
    return replace(task, state=ReviewTaskState.resolved), updated
