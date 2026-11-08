"""DOM-080/081: public cells and public provider activity."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from app.domain.indicators import compute_snapshot
from app.domain.public import band, public_activities, public_cells
from app.domain.types import (
    Activity,
    ActivityStatus,
    ActivityType,
    AreaLevel,
    Bucket,
    CoverageLabel,
    IndicatorCell,
    NeedCategory,
    ProviderOrganization,
    PublicActivity,
    PublicIndicatorCell,
    Schedule,
    Service,
    ServiceStatus,
    VettingStatus,
    Visibility,
)

from .factories import AREAS, ORG, T0, obs, protective, report, reporters_in, standard

END = T0 + timedelta(hours=6)


def snap(reports, profile):
    return compute_snapshot(ORG, reports, AREAS, profile, Bucket.h24, END, END)


@pytest.mark.parametrize("n,b", [(0, "0"), (1, "1–4"), (4, "1–4"), (5, "5–9"), (10, "10–24"), (24, "10–24"),
                                 (25, "25–49"), (99, "50–99"), (100, "100+"), (5000, "100+")])
def test_bands(n, b):
    assert band(n) == b


class TestPublicCells:
    def test_disabled_by_default_in_protective(self):
        p = protective()
        assert public_cells(snap(reporters_in("S1", 20), p), p, END + timedelta(days=2)) == []

    def test_delay_applies(self):
        p = protective(public_dashboard_enabled=True)
        s = snap(reporters_in("S1", 12), p)
        assert public_cells(s, p, END + timedelta(hours=23)) == []
        assert public_cells(s, p, END + timedelta(hours=24)) != []

    def test_public_level_is_coarser(self):
        p = protective(public_dashboard_enabled=True)
        cells = public_cells(snap(reporters_in("S1", 12), p), p, END + timedelta(days=1))
        assert cells and all(c.level is AreaLevel.parish for c in cells)

    def test_banded_counts_and_public_k(self):
        p = protective(public_dashboard_enabled=True)
        reps = reporters_in("S1", 12) + reporters_in("S4", 5)
        cells = {(c.area_id, c.subject): c for c in public_cells(snap(reps, p), p, END + timedelta(days=1))}
        p1 = cells[("P1", NeedCategory.water_drinking)]
        assert p1.need_count_band == "10–24" and p1.coverage is CoverageLabel.reported and p1.freshness is not None
        p2 = cells[("P2", NeedCategory.water_drinking)]  # 5 >= aggregate k but < public k 10
        assert p2.need_count_band is None and p2.coverage is CoverageLabel.thin and p2.freshness is None

    def test_status_mix_banded(self):
        p = standard()
        reps = [report(key=f"k{i}", observations=[obs(Service.electricity, ServiceStatus.unavailable)]) for i in range(7)]
        cells = {(c.area_id, c.subject): c for c in public_cells(snap(reps, p), p, END)}
        assert cells[("S1", Service.electricity)].status_mix_bands == {ServiceStatus.unavailable: "5–9"}

    def test_unknown_stays_unknown(self):
        p = standard()
        cells = {(c.area_id, c.subject): c for c in public_cells(snap([], p), p, END)}
        c = cells[("S2", NeedCategory.charging)]
        assert c.coverage is CoverageLabel.none and c.need_count_band is None

    def test_public_model_is_separate_and_minimal(self):
        assert not issubclass(PublicIndicatorCell, IndicatorCell)
        fields = {f.name for f in dataclasses.fields(PublicIndicatorCell)}
        assert fields == {"area_id", "level", "subject", "bucket", "bucket_end", "coverage", "need_count_band",
                          "status_mix_bands", "freshness"}

    def test_other_org_snapshot_rejected(self):
        p = standard()
        s = snap(reporters_in("S1", 10), p)
        other = dataclasses.replace(p, org_id="x")
        assert public_cells(s, other, END) == []


class TestPublicActivities:
    def test_only_public_marked(self):
        provs = {
            "p1": ProviderOrganization("p1", ORG, "Agua Ya", VettingStatus.vetted, frozenset(), frozenset()),
            "p2": ProviderOrganization("p2", ORG, "Bad", VettingStatus.suspended, frozenset(), frozenset()),
        }

        def a(i, vis, prov="p1", status=ActivityStatus.active):
            return Activity(i, prov, ActivityType.charging_point, NeedCategory.charging, frozenset({"S1"}),
                            Schedule(True, "lun–vie 9–17"), status, T0, visibility=vis, public_location_id="mp1")

        acts = [a("a1", Visibility.public), a("a2", Visibility.tenant), a("a3", Visibility.internal_only),
                a("a4", Visibility.public, "p2"), a("a5", Visibility.public, status=ActivityStatus.ended)]
        out = public_activities(acts, provs, standard())
        assert out == [PublicActivity("Agua Ya", ActivityType.charging_point, frozenset({"S1"}), "lun–vie 9–17", "mp1")]
        assert public_activities(acts, provs, protective()) == []  # dashboard off
