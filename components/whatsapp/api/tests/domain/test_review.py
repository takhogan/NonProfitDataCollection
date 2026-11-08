"""DOM-070..074: comparison, dispositions, and the no-automatic-exclusion property."""
from __future__ import annotations

import random
from dataclasses import replace
from datetime import timedelta

import pytest

from app.domain.errors import Forbidden, InvalidTransition, ValidationFailed
from app.domain.indicators import IndicatorMethod, compute_snapshot, reporter_identity
from app.domain.needs import RefreshReply, apply_refresh_reply, tick_need
from app.domain.ports import SequentialIds
from app.domain.reports import is_aggregatable, link_repeat
from app.domain.review import (
    ComparisonRule,
    attach_external_evidence,
    compare,
    detect_floods,
    detect_outlier_cells,
    evidence_review_tasks,
    find_comparisons,
    flag_urgent,
    mark_pending,
    resolve_review,
    tasks_from_comparisons,
)
from app.domain.types import (
    AreaLevel,
    Bucket,
    ComparisonKind,
    Disposition,
    ExternalContext,
    NeedCategory,
    ReportState,
    ReviewDisposition,
    ReviewTaskKind,
    ReviewTaskState,
    Role,
    Service,
    ServiceStatus,
)

from .factories import AREAS, ORG, T0, ctx, need, obs, protective, report, reporters_in

PW = Service.piped_water


def r_status(key, status, at=T0, area="S1", **kw):
    return report(key=key, area=area, at=at, observations=[obs(PW, status, at)], **kw)


class TestComparison:
    def test_conflict_between_different_reporters_overlapping(self):
        a, b = r_status("a", ServiceStatus.available), r_status("b", ServiceStatus.unavailable, T0 + timedelta(hours=2))
        (c,) = compare(a, b)
        assert c.kind is ComparisonKind.conflict and c.rule_version == "compare-1"
        assert "same_area" in c.reasons and "overlapping_time" in c.reasons

    def test_same_reporter_change_is_transition(self):
        a, b = r_status("a", ServiceStatus.unavailable), r_status("a", ServiceStatus.available, T0 + timedelta(hours=3))
        (c,) = compare(a, b)
        assert c.kind is ComparisonKind.transition
        assert tasks_from_comparisons([c], SequentialIds(), T0) == []

    @pytest.mark.parametrize(
        "b",
        [
            r_status("b", ServiceStatus.unavailable, T0 + timedelta(hours=7)),  # no overlap
            r_status("b", ServiceStatus.unavailable, area="S2"),  # other area
            r_status("b", ServiceStatus.unknown),  # unknown never conflicts
            report(key="b", observations=[obs(Service.electricity, ServiceStatus.unavailable)]),  # other service
            r_status("b", ServiceStatus.unavailable, state=ReportState.draft),  # not confirmed
        ],
    )
    def test_incompatible_pairs_not_compared(self, b):
        assert compare(r_status("a", ServiceStatus.available), b) == []

    def test_duplicate_candidate_by_source_digest(self):
        a = r_status("a", ServiceStatus.unavailable, source_digest="h1")
        b = r_status("b", ServiceStatus.unavailable, source_digest="h1")
        (c,) = compare(a, b)
        assert c.kind is ComparisonKind.duplicate_candidate
        (t,) = tasks_from_comparisons([c], SequentialIds(), T0)
        assert t.kind is ReviewTaskKind.duplicate_candidate and t.rule_version == "compare-1"

    def test_find_and_mark_pending_keeps_counting(self):
        reps = [r_status("a", ServiceStatus.available), r_status("b", ServiceStatus.unavailable),
                r_status("c", ServiceStatus.unavailable)]
        tasks = tasks_from_comparisons(find_comparisons(reps), SequentialIds(), T0)
        assert len(tasks) == 2 and all(t.kind is ReviewTaskKind.conflicting_observation for t in tasks)
        marked = mark_pending(reps, tasks)
        assert all(r.pending_review and is_aggregatable(r) for r in marked)


class TestTaskSources:
    def test_floods_open_tasks_without_excluding(self):
        reps = reporters_in("S1", 5)
        (t,) = detect_floods(reps, T0 + timedelta(minutes=10), SequentialIds(), ComparisonRule(flood_threshold=5))
        assert t.kind is ReviewTaskKind.flood and t.area_id == "S1" and len(t.report_ids) == 5
        assert all(is_aggregatable(r) for r in reps)

    def test_outlier_cell(self):
        prof = protective()
        prev = compute_snapshot(ORG, reporters_in("S1", 3, at=T0 - timedelta(hours=5)), AREAS, prof, Bucket.h6, T0, T0)
        end = T0 + timedelta(hours=6)
        cur_reps = reporters_in("S1", 9, prefix="y")
        cur = compute_snapshot(ORG, cur_reps, AREAS, prof, Bucket.h6, end, end)
        tasks = detect_outlier_cells(cur, prev, SequentialIds(), end, k=prof.aggregate_k)
        (t,) = [t for t in tasks if t.area_id == "S1"]
        assert t.kind is ReviewTaskKind.outlier_cell and "spike_3_to_9" in t.reasons
        assert all(is_aggregatable(r) for r in cur_reps)
        # a modest rise is not an outlier
        cur2 = compute_snapshot(ORG, reporters_in("S1", 5, prefix="z"), AREAS, prof, Bucket.h6, end, end)
        assert not [t for t in detect_outlier_cells(cur2, prev, SequentialIds(), end, k=3) if t.area_id == "S1"]

    def test_external_evidence_never_changes_reports(self):
        reps = [r_status(f"k{i}", ServiceStatus.unavailable, T0 + timedelta(hours=1)) for i in range(4)]
        ext = ExternalContext("S1", PW, "monitor_ciudad", ServiceStatus.available, T0 + timedelta(hours=1))
        ctx_out, same = attach_external_evidence(ext, reps)
        assert same == reps and ctx_out is ext
        end = T0 + timedelta(hours=2)
        snap = compute_snapshot(ORG, reps, AREAS, protective(), Bucket.h6, end, end, [ext])
        tasks = evidence_review_tasks(snap, SequentialIds(), end)
        assert tasks and all(t.report_ids == () for t in tasks)
        assert all(is_aggregatable(r) for r in reps)


def _task(rids, kind=ReviewTaskKind.duplicate_candidate):
    from app.domain.types import ReviewTask

    return ReviewTask("rt1", kind, tuple(rids), ReviewTaskState.open, T0)


def _decision(d, **kw):
    return ReviewDisposition("rt1", d, "rev1", kw.pop("rationale", "checked"), T0, **kw)


REVIEWER = ctx(Role.reviewer, actor="rev1")


class TestDispositions:
    def setup_method(self):
        self.a, self.b = report(key="a", needs=[need()]), report(key="b", needs=[need()])
        self.reps = {self.a.id: self.a, self.b.id: self.b}

    def test_duplicate_merges_counted_once(self):
        task, out = resolve_review(REVIEWER, _task([self.a.id, self.b.id]),
                                   _decision(Disposition.duplicate, primary_report_id=self.a.id), self.reps)
        assert task.state is ReviewTaskState.resolved
        by = {r.id: r for r in out}
        assert is_aggregatable(by[self.a.id]) and not is_aggregatable(by[self.b.id])
        assert by[self.b.id].duplicate_of_id == self.a.id

    def test_spam_excluded_with_reason(self):
        _, out = resolve_review(REVIEWER, _task([self.a.id]), _decision(Disposition.spam, rationale="bot burst"),
                                self.reps)
        assert out[0].exclusion_reason == "bot burst" and not is_aggregatable(out[0])

    @pytest.mark.parametrize("d", [Disposition.valid, Disposition.unresolved])
    def test_non_excluding_dispositions(self, d):
        _, out = resolve_review(REVIEWER, _task([self.a.id]), _decision(d, review_after=T0 + timedelta(days=3)),
                                self.reps)
        assert is_aggregatable(out[0]) and out[0].disposition is d
        assert out[0].pending_review is (d is Disposition.unresolved)

    def test_location_corrected(self):
        _, out = resolve_review(REVIEWER, _task([self.a.id], ReviewTaskKind.unresolved_location),
                                _decision(Disposition.location_corrected, corrected_area_id="S2"), self.reps)
        assert out[0].area_id == "S2" and is_aggregatable(out[0])
        with pytest.raises(ValidationFailed):
            resolve_review(REVIEWER, _task([self.a.id]), _decision(Disposition.location_corrected), self.reps)

    def test_rules(self):
        with pytest.raises(Forbidden):
            resolve_review(ctx(Role.coordinator, actor="rev1"), _task([self.a.id]), _decision(Disposition.valid), self.reps)
        with pytest.raises(ValidationFailed):
            resolve_review(REVIEWER, _task([self.a.id]), _decision(Disposition.valid, rationale="  "), self.reps)
        with pytest.raises(ValidationFailed):
            resolve_review(REVIEWER, _task([self.a.id]), _decision(Disposition.duplicate, primary_report_id=self.a.id),
                           self.reps)
        with pytest.raises(Forbidden):
            resolve_review(ctx(Role.reviewer, actor="someone"), _task([self.a.id]), _decision(Disposition.valid), self.reps)
        done = replace(_task([self.a.id]), state=ReviewTaskState.resolved)
        with pytest.raises(InvalidTransition):
            resolve_review(REVIEWER, done, _decision(Disposition.valid), self.reps)
        other = {self.a.id: replace(self.a, org_id="x")}
        with pytest.raises(Forbidden):
            resolve_review(REVIEWER, _task([self.a.id]), _decision(Disposition.valid), other)


# ---------------------------------------------------------------------------
# DOM-073 property: no rule excludes a report without a human duplicate/spam.
# ---------------------------------------------------------------------------

AREA_IDS = ("S1", "S2", "S3", "S4")
MUNICIPALITY = IndicatorMethod(cell_levels=(AreaLevel.municipality,))
OPS = ("compare", "flag_urgent", "flood", "external", "link_repeat", "tick", "refresh", "valid", "unresolved",
       "location", "duplicate", "spam")


def _random_reports(rng: random.Random, n: int):
    out = []
    for i in range(n):
        at = T0 + timedelta(minutes=rng.randrange(0, 600))
        statuses = list(ServiceStatus)
        out.append(
            report(
                id=f"r{i}",
                key=rng.choice([None, "kA", "kB", "kC", f"u{i}"]),
                area=rng.choice(AREA_IDS),
                at=at,
                observations=[obs(rng.choice(list(Service)), rng.choice(statuses), at)],
                needs=[need(rng.choice(list(NeedCategory)), at=at)] if rng.random() < 0.7 else [],
                source_digest=rng.choice([None, None, "dupA", "dupB"]),
                pending_review=rng.random() < 0.3,
            )
        )
    return out


def run_operations(reports, ops, rng: random.Random):
    """Apply a sequence of domain commands; return final reports and the ids that a
    human excluded via a duplicate/spam disposition."""
    ids = SequentialIds()
    state = {r.id: r for r in reports}
    human_excluded: set[str] = set()
    now = T0 + timedelta(hours=11)
    for op in ops:
        cur = list(state.values())
        if op == "compare":
            tasks = tasks_from_comparisons(find_comparisons(cur), ids, now)
            state.update({r.id: r for r in mark_pending(cur, tasks)})
        elif op == "flag_urgent" and cur:
            r, _ = flag_urgent(rng.choice(cur), ids, now)
            state[r.id] = r
        elif op == "flood":
            tasks = detect_floods(cur, now, ids, ComparisonRule(flood_threshold=2, flood_window=timedelta(hours=12)))
            state.update({r.id: r for r in mark_pending(cur, tasks)})
        elif op == "external":
            ext = ExternalContext(rng.choice(AREA_IDS), rng.choice(list(Service)), "monitor_ciudad",
                                  rng.choice(list(ServiceStatus)), now, large_outage=True)
            _, same = attach_external_evidence(ext, cur)
            snap = compute_snapshot(ORG, same, AREAS, protective(), Bucket.d7, now, now, [ext])
            evidence_review_tasks(snap, ids, now)
        elif op == "link_repeat" and cur:
            r = rng.choice(cur)
            linked, replaced = link_repeat(r, cur, now)
            state[linked.id] = linked
            for n in replaced:
                owner = state[n.report_id]
                state[owner.id] = replace(owner, needs=tuple(n if x.id == n.id else x for x in owner.needs))
        elif op == "tick":
            for r in cur:
                state[r.id] = replace(r, needs=tuple(tick_need(n, now + timedelta(days=rng.randrange(0, 20)))
                                                     for n in r.needs))
        elif op == "refresh" and cur:
            r = rng.choice(cur)
            reply = RefreshReply(still_needs=rng.choice([True, False, None]), service=Service.piped_water,
                                 service_status=ServiceStatus.available)
            state[r.id] = replace(r, needs=tuple(apply_refresh_reply(n, reply, now)[0] for n in r.needs))
        elif op in ("valid", "unresolved", "location", "duplicate", "spam") and cur:
            picks = rng.sample(cur, k=min(len(cur), 2))
            task = _task([p.id for p in picks])
            d = {"valid": Disposition.valid, "unresolved": Disposition.unresolved,
                 "location": Disposition.location_corrected, "duplicate": Disposition.duplicate,
                 "spam": Disposition.spam}[op]
            kw = {}
            if d is Disposition.duplicate:
                if len(picks) < 2:
                    continue
                kw["primary_report_id"] = picks[0].id
            if d is Disposition.location_corrected:
                kw["corrected_area_id"] = rng.choice(AREA_IDS)
            _, updated = resolve_review(REVIEWER, task, _decision(d, **kw), state)
            for u in updated:
                state[u.id] = u
                if u.disposition in (Disposition.duplicate, Disposition.spam):
                    human_excluded.add(u.id)
                else:
                    human_excluded.discard(u.id)
    return list(state.values()), human_excluded


def assert_no_automatic_exclusion(initial, ops, rng):
    final, human_excluded = run_operations(initial, ops, rng)
    included = {r.id for r in final if is_aggregatable(r)}
    expected = {r.id for r in initial if is_aggregatable(r)} - human_excluded
    assert included == expected
    for r in final:
        if r.id not in included:
            assert r.disposition in (Disposition.duplicate, Disposition.spam) and r.id in human_excluded
    # And the aggregation itself counts every included report's source.
    end = T0 + timedelta(hours=12)
    snap = compute_snapshot(ORG, final, AREAS, protective(), Bucket.h24, end, end, method=MUNICIPALITY)
    by_final = {r.id: r for r in final}
    for c in snap.cells:
        if isinstance(c.subject, Service):
            sources = {reporter_identity(by_final[i]) for i in included
                       if any(o.service is c.subject for o in by_final[i].observations)}
        else:
            sources = {reporter_identity(by_final[i]) for i in included
                       if any(n.category is c.subject for n in by_final[i].needs)}
        if len(sources) >= 3:
            assert c.distinct_reporters == len(sources)
        else:
            assert c.distinct_reporters is None


@pytest.mark.parametrize("seed", range(60))
def test_no_automatic_exclusion_seeded(seed):
    rng = random.Random(seed)
    initial = _random_reports(rng, rng.randrange(1, 14))
    ops = [rng.choice(OPS) for _ in range(rng.randrange(1, 12))]
    assert_no_automatic_exclusion(initial, ops, rng)


@pytest.mark.parametrize("seed", range(20))
def test_machine_rules_alone_never_exclude(seed):
    rng = random.Random(1000 + seed)
    initial = _random_reports(rng, 12)
    machine_ops = [rng.choice(OPS[:7]) for _ in range(10)]
    final, human = run_operations(initial, machine_ops, rng)
    assert human == set()
    assert {r.id for r in final if is_aggregatable(r)} == {r.id for r in initial}


hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


@settings(max_examples=150, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), n=st.integers(1, 15), ops=st.lists(st.sampled_from(OPS), max_size=15))
def test_no_automatic_exclusion_property(seed, n, ops):
    rng = random.Random(seed)
    assert_no_automatic_exclusion(_random_reports(rng, n), ops, rng)
