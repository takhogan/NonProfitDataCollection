"""DOM-040..046: indicator cells, coverage, suppression, confidence, ranking."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.indicators import (
    DEFAULT_RANKING_CRITERIA,
    IndicatorMethod,
    compute_snapshot,
    confidence_for,
    coverage_label,
    rank_areas,
)
from app.domain.types import (
    Bucket,
    ConfidenceLabel,
    CoverageLabel,
    ExternalAgreement,
    ExternalContext,
    NeedCategory,
    NeedState,
    RemainingSupply,
    Service,
    ServiceStatus,
    Urgency,
)

from .factories import AREAS, ORG, OTHER_ORG, T0, need, obs, protective, report, reporters_in, standard

END = T0 + timedelta(hours=6)
W = NeedCategory.water_drinking


def cell(snap, area, subject=W):
    return next(c for c in snap.cells if c.area_id == area and c.subject == subject)


def snap(reports, profile=None, bucket=Bucket.h24, end=END, now=END, external=()):
    return compute_snapshot(ORG, reports, AREAS, profile or protective(), bucket, end, now, external)


class TestCells:
    def test_one_cell_per_area_subject_for_sector_and_parish(self):
        s = snap([])
        areas = {c.area_id for c in s.cells}
        assert areas == {"P1", "P2", "S1", "S2", "S3", "S4"}
        assert len(s.cells) == 6 * 5  # 3 need categories + 2 services

    def test_counts_for_reported_cell(self):
        reps = [
            report(key="a", needs=[need(urgency=Urgency.urgent, supply=RemainingSupply.none, people=4)]),
            report(key="b", needs=[need(urgency=Urgency.urgent, supply=RemainingSupply.little, people=2)]),
            report(key="c", needs=[need(urgency=Urgency.soon, supply=RemainingSupply.unknown)]),
            report(key="d", needs=[need(state=NeedState.resolved_by_reporter, people=9)]),
        ]
        c = cell(snap(reps), "S1")
        assert c.coverage is CoverageLabel.reported and not c.suppressed
        assert c.distinct_reporters == 4
        assert c.active_needs == 3 and c.urgent_active_needs == 2
        assert c.people_affected_known == 6
        assert c.people_affected_unknown_count == 1
        assert c.urgency_mix == {Urgency.urgent: 2, Urgency.soon: 1}
        assert c.supply_mix == {RemainingSupply.none: 1, RemainingSupply.little: 1, RemainingSupply.unknown: 1}
        assert c.status_mix is None
        assert c.distinct_households is None and c.unit_label == "reportantes"
        assert c.freshness == T0 and c.oldest_active_need_at == T0

    def test_parish_merges_sector_data(self):
        reps = reporters_in("S1", 2) + reporters_in("S2", 2)
        s = snap(reps)
        assert cell(s, "S1").suppressed and cell(s, "S2").suppressed
        assert cell(s, "S1").merged_into_area_id == "P1"
        p = cell(s, "P1")
        assert not p.suppressed and p.distinct_reporters == 4 and p.active_needs == 4

    def test_service_status_mix_uses_latest_per_reporter(self):
        reps = [
            report(key="a", at=T0, observations=[obs(Service.piped_water, ServiceStatus.unavailable, T0)]),
            report(key="a", at=T0 + timedelta(hours=2),
                   observations=[obs(Service.piped_water, ServiceStatus.available, T0 + timedelta(hours=2))]),
            report(key="b", observations=[obs(Service.piped_water, ServiceStatus.intermittent)]),
            report(key="c", observations=[obs(Service.piped_water, ServiceStatus.unknown)]),
        ]
        c = cell(snap(reps), "S1", Service.piped_water)
        assert c.status_mix == {
            ServiceStatus.available: 1,
            ServiceStatus.intermittent: 1,
            ServiceStatus.unknown: 1,
        }
        assert c.freshness == T0 + timedelta(hours=2)
        assert c.active_needs is None  # not a need subject

    def test_bucket_window(self):
        old = reporters_in("S1", 3, at=T0 - timedelta(hours=7))
        new = reporters_in("S1", 3, at=T0, prefix="n")
        assert cell(snap(old + new, bucket=Bucket.h6), "S1").distinct_reporters == 3
        assert cell(snap(old + new, bucket=Bucket.h24), "S1").distinct_reporters == 6
        future = reporters_in("S2", 3, at=END + timedelta(minutes=1))
        assert cell(snap(future), "S2").coverage is CoverageLabel.none

    def test_other_org_reports_ignored(self):
        reps = reporters_in("S1", 3)
        other = [report(org=OTHER_ORG, key=f"o{i}", needs=[need()]) for i in range(5)]
        assert cell(snap(reps + other), "S1").distinct_reporters == 3

    def test_households_in_standard_profile(self):
        reps = [
            report(key="phone1", household="h1", needs=[need()]),
            report(key="phone1", household="h2", needs=[need()], at=T0 + timedelta(minutes=1)),
            report(key="phone2", household="h3", needs=[need()]),
            report(key="phone3", household="h4", needs=[need()]),
        ]
        c = cell(snap(reps, profile=standard()), "S1")
        assert c.unit_label == "hogares"
        assert c.distinct_households is not None

    def test_snapshot_metadata(self):
        reps = reporters_in("S1", 3)
        s = snap(reps, profile=protective(version=7))
        assert s.method_version == "indicators-1"
        assert s.profile_version == 7
        assert s.input_watermark is not None and reps[-1].id in s.input_watermark
        assert s.bucket is Bucket.h24 and s.bucket_end == END and s.computed_at == END
        assert all(c.method_version == "indicators-1" for c in s.cells)

    def test_deterministic(self):
        reps = reporters_in("S1", 4) + reporters_in("S3", 5)
        assert snap(reps) == snap(list(reversed(reps)))


class TestUnknownIsNotZero:
    def test_area_without_reports_is_none_not_zero(self):
        c = cell(snap(reporters_in("S1", 3)), "S2")
        assert c.coverage is CoverageLabel.none
        assert c.active_needs is None and c.distinct_reporters is None and c.people_affected_known is None
        assert c.confidence.label is ConfidenceLabel.low and "no_reports" in c.confidence.reasons

    def test_service_cell_without_reports_is_not_ok(self):
        c = cell(snap([]), "S1", Service.electricity)
        assert c.coverage is CoverageLabel.none and c.status_mix is None

    def test_reported_zero_active_needs_is_real_zero(self):
        reps = [report(key=f"k{i}", needs=[need(state=NeedState.resolved_by_reporter)]) for i in range(3)]
        c = cell(snap(reps), "S1")
        assert c.coverage is CoverageLabel.reported and c.active_needs == 0

    @pytest.mark.parametrize("n,k,label", [(0, 3, "none"), (1, 3, "thin"), (2, 3, "thin"), (3, 3, "reported"), (4, 5, "thin")])
    def test_coverage_label(self, n, k, label):
        assert coverage_label(n, k).value == label


class TestSuppression:
    @pytest.mark.parametrize("n", [1, 2])
    def test_below_k_suppressed_everywhere(self, n):
        c = cell(snap(reporters_in("S4", n)), "S4")
        assert c.suppressed and c.coverage is CoverageLabel.thin
        for f in ("active_needs", "urgent_active_needs", "distinct_reporters", "people_affected_known",
                  "people_affected_unknown_count", "urgency_mix", "supply_mix", "freshness",
                  "oldest_active_need_at", "pending_review_share", "input_watermark"):
            assert getattr(c, f) is None, f
        assert cell(snap(reporters_in("S4", n)), "P2").suppressed  # parent also < k

    def test_k_from_profile(self):
        reps = reporters_in("S1", 4)
        assert not cell(snap(reps, profile=protective(aggregate_k=3)), "S1").suppressed
        assert cell(snap(reps, profile=protective(aggregate_k=5, public_k=10)), "S1").suppressed

    def test_secondary_suppression_prevents_subtraction(self):
        reps = reporters_in("S1", 2) + reporters_in("S2", 3) + reporters_in("S3", 5)
        s = snap(reps)
        assert cell(s, "S1").suppressed
        assert cell(s, "S2").suppressed  # smallest visible sibling
        assert "secondary_suppression" in cell(s, "S2").confidence.reasons
        assert not cell(s, "S3").suppressed
        assert cell(s, "P1").distinct_reporters == 10

    def test_no_secondary_needed_when_two_suppressed(self):
        reps = reporters_in("S1", 1) + reporters_in("S2", 2) + reporters_in("S3", 5)
        s = snap(reps)
        assert not cell(s, "S3").suppressed

    def test_repeat_reports_do_not_lift_cell_over_k(self):
        reps = [report(key="same", at=T0 + timedelta(minutes=i), needs=[need()]) for i in range(10)]
        assert cell(snap(reps), "S1").suppressed


class TestConfidence:
    def test_many_fresh_reviewed_sources_high(self):
        c = cell(snap(reporters_in("S1", 6, at=END - timedelta(hours=1))), "S1")
        assert c.confidence.label is ConfidenceLabel.high
        assert "multiple_independent_sources" in c.confidence.reasons and "fresh_data" in c.confidence.reasons

    def test_unreviewed_lowers_but_still_counts(self):
        reps = [report(key=f"k{i}", needs=[need()], pending_review=True, at=END - timedelta(hours=1)) for i in range(6)]
        c = cell(snap(reps), "S1")
        assert c.active_needs == 6
        assert c.confidence.label is ConfidenceLabel.medium and "mostly_unreviewed" in c.confidence.reasons
        assert c.pending_review_share == 1.0

    def test_stale_and_unreviewed_low(self):
        reps = [report(key=f"k{i}", needs=[need()], pending_review=True, at=T0 - timedelta(hours=10)) for i in range(6)]
        c = cell(snap(reps, now=T0 + timedelta(hours=30)), "S1")
        assert c.confidence.label is ConfidenceLabel.low
        assert {"mostly_unreviewed", "stale_data"} <= set(c.confidence.reasons)

    def test_external_disagreement_lowers_confidence_only(self):
        reps = [report(key=f"k{i}", observations=[obs(Service.piped_water, ServiceStatus.unavailable, END - timedelta(hours=1))],
                       at=END - timedelta(hours=1)) for i in range(6)]
        ext = [ExternalContext("P1", Service.piped_water, "monitor_ciudad", ServiceStatus.available, END - timedelta(hours=2))]
        base = cell(snap(reps), "S1", Service.piped_water)
        with_ext = cell(snap(reps, external=ext), "S1", Service.piped_water)
        assert base.confidence.label is ConfidenceLabel.high
        assert with_ext.confidence.label is ConfidenceLabel.medium
        assert "external_disagrees:monitor_ciudad" in with_ext.confidence.reasons
        # DOM-045: separate layer — counts unchanged
        assert base.status_mix == with_ext.status_mix and base.distinct_reporters == with_ext.distinct_reporters

    def test_external_agreement_reason(self):
        reps = reporters_in("S1", 3, at=END - timedelta(hours=1))
        ext = [ExternalContext("S1", Service.piped_water, "monitor_ciudad", ServiceStatus.unavailable, END - timedelta(hours=1))]
        assert "external_agrees:monitor_ciudad" in cell(snap(reps, external=ext), "S1").confidence.reasons

    def test_confidence_rule_table(self):
        kw = dict(k=3, now=END, freshness=END, external_source=None)
        assert confidence_for(units=0, pending_share=None, agreement=ExternalAgreement.no_data, **kw).label is ConfidenceLabel.low
        assert confidence_for(units=2, pending_share=0, agreement=ExternalAgreement.no_data, **kw).label is ConfidenceLabel.low
        assert confidence_for(units=4, pending_share=0, agreement=ExternalAgreement.no_data, **kw).label is ConfidenceLabel.medium
        assert confidence_for(units=6, pending_share=0, agreement=ExternalAgreement.no_data, **kw).label is ConfidenceLabel.high
        every = confidence_for(units=6, pending_share=0.2, agreement=ExternalAgreement.agrees, **kw)
        assert every.reasons  # always explained


class TestRanking:
    def test_declared_order(self):
        reps = (
            reporters_in("S1", 3, urgency=Urgency.urgent)
            + reporters_in("S2", 3, urgency=Urgency.urgent)
            + reporters_in("S2", 1, urgency=Urgency.urgent, prefix="x")
            + reporters_in("S3", 4, urgency=Urgency.soon)
            + reporters_in("S4", 3, at=T0 - timedelta(hours=3))
        )
        ranked = rank_areas(snap(reps).cells)
        order = [(a.cell.area_id, a.rank) for a in ranked if a.cell.level.value == "sector"]
        assert [a for a, _ in order] == ["S2", "S1", "S4", "S3"]
        assert all(a.criteria == DEFAULT_RANKING_CRITERIA and a.method_version == "indicators-1" for a in ranked)

    def test_oldest_need_breaks_ties(self):
        reps = reporters_in("S1", 3, at=T0) + reporters_in("S3", 3, at=T0 - timedelta(hours=5))
        ranked = [a.cell.area_id for a in rank_areas(snap(reps).cells) if a.cell.level.value == "sector"]
        assert ranked == ["S3", "S1"]

    def test_suppressed_and_unknown_not_ranked(self):
        reps = reporters_in("S1", 2) + reporters_in("S4", 3)
        ranked = {a.cell.area_id for a in rank_areas(snap(reps).cells)}
        assert ranked == {"S4", "P2"}  # S1 suppressed, S2/S3 unknown, P1 < k

    def test_undeclared_criteria_rejected(self):
        with pytest.raises(ValueError):
            rank_areas([], IndicatorMethod(ranking_criteria=("secret_weight",)))
