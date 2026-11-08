"""DOM-050..055: vetting, activities, coverage, contact list, alerts."""
from __future__ import annotations

import dataclasses
from dataclasses import replace
from datetime import timedelta

import pytest

from app.domain.errors import Forbidden, InvalidTransition, ValidationFailed
from app.domain.indicators import compute_snapshot
from app.domain.providers import (
    activity_view,
    change_vetting,
    compute_coverage,
    confirm_activity,
    display_status,
    evaluate_alerts,
    log_activity,
    select_contact_list,
    transition_activity,
)
from app.domain.types import (
    Activity,
    ActivityDisplayStatus,
    ActivityStatus,
    ActivityType,
    Alert,
    AlertSubscription,
    AlertTrigger,
    Bucket,
    ContactField,
    CoverageStatus,
    ExternalContext,
    NeedCategory,
    NeedState,
    Permission,
    PermissionPurpose,
    ProviderOrganization,
    ReporterContact,
    Role,
    Schedule,
    Service,
    ServiceStatus,
    Urgency,
    VettingStatus,
    Visibility,
)

from .factories import AREAS, ORG, T0, ctx, need, protective, report, reporters_in, standard

W, C = NeedCategory.water_drinking, NeedCategory.charging
END = T0 + timedelta(hours=6)


def provider(**kw) -> ProviderOrganization:
    base = dict(id="prov1", org_id=ORG, name="Agua Ya", vetting=VettingStatus.vetted,
                scope_area_ids=frozenset({"P1"}), scope_categories=frozenset({W}))
    base.update(kw)
    return ProviderOrganization(**base)


def activity(**kw) -> Activity:
    base = dict(id="act1", provider_id="prov1", type=ActivityType.water_distribution_point, category=W,
                area_ids=frozenset({"S1"}), schedule=Schedule(True, "sáb 8–12"), status=ActivityStatus.active,
                last_confirmed_at=T0)
    base.update(kw)
    return Activity(**base)


def snap(reports, profile=None):
    return compute_snapshot(ORG, reports, AREAS, profile or protective(), Bucket.h24, END, END)


class TestVetting:
    def test_admin_vets_with_reason(self):
        ch = change_vetting(ctx(Role.org_admin), provider(vetting=VettingStatus.unvetted), VettingStatus.vetted,
                            "statement v1 signed", T0)
        assert ch.provider.vetting is VettingStatus.vetted and ch.provider.version == 2
        assert not ch.revoke_access and ch.actor_id == "user_1"

    def test_suspension_revokes_access(self):
        ch = change_vetting(ctx(Role.org_admin), provider(), VettingStatus.suspended, "data misuse", T0)
        assert ch.revoke_access

    @pytest.mark.parametrize("role", [Role.coordinator, Role.provider, Role.reviewer])
    def test_only_admin(self, role):
        with pytest.raises(Forbidden):
            change_vetting(ctx(role), provider(), VettingStatus.suspended, "x", T0)

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_reason_required(self, reason):
        with pytest.raises(ValidationFailed):
            change_vetting(ctx(Role.org_admin), provider(), VettingStatus.suspended, reason, T0)

    def test_invalid_transition(self):
        with pytest.raises(InvalidTransition):
            change_vetting(ctx(Role.org_admin), provider(vetting=VettingStatus.vetted), VettingStatus.unvetted, "x", T0)

    def test_other_org(self):
        with pytest.raises(Forbidden):
            change_vetting(ctx(Role.org_admin, org="x"), provider(), VettingStatus.suspended, "r", T0)


class TestActivities:
    def test_log_and_lifecycle(self):
        a = log_activity(ctx(Role.provider, provider="prov1"), provider(), "a1", type=ActivityType.water_delivery,
                         category=W, area_ids=frozenset({"S1"}), schedule=Schedule(False, "hoy 9–11"), now=T0)
        assert a.status is ActivityStatus.planned and a.last_confirmed_at == T0
        a = transition_activity(a, ActivityStatus.active, T0 + timedelta(hours=1))
        a = transition_activity(a, ActivityStatus.paused, T0 + timedelta(hours=2))
        a = transition_activity(a, ActivityStatus.ended, T0 + timedelta(hours=3))
        with pytest.raises(InvalidTransition):
            transition_activity(a, ActivityStatus.active, T0)

    def test_other_provider_cannot_log(self):
        with pytest.raises(Forbidden):
            log_activity(ctx(Role.provider, provider="prov2"), provider(), "a1", type=ActivityType.other,
                         category=W, area_ids=frozenset({"S1"}), schedule=Schedule(False, "x"), now=T0)

    def test_suspended_cannot_log(self):
        with pytest.raises(Forbidden):
            log_activity(ctx(Role.provider, provider="prov1"), provider(vetting=VettingStatus.suspended), "a1",
                         type=ActivityType.other, category=W, area_ids=frozenset({"S1"}),
                         schedule=Schedule(False, "x"), now=T0)

    def test_schedule_and_area_validation(self):
        c = ctx(Role.provider, provider="prov1")
        with pytest.raises(ValidationFailed):
            log_activity(c, provider(), "a", type=ActivityType.other, category=W, area_ids=frozenset(),
                         schedule=Schedule(False, "x"), now=T0)
        with pytest.raises(ValidationFailed):
            log_activity(c, provider(), "a", type=ActivityType.other, category=W, area_ids=frozenset({"S1"}),
                         schedule=Schedule(False, "x", starts_at=T0, ends_at=T0 - timedelta(hours=1)), now=T0)

    def test_unconfirmed_after_7_days(self):
        a = activity()
        assert display_status(a, T0 + timedelta(days=6, hours=23)) is ActivityDisplayStatus.active
        assert display_status(a, T0 + timedelta(days=7)) is ActivityDisplayStatus.unconfirmed
        assert display_status(confirm_activity(a, T0 + timedelta(days=7)), T0 + timedelta(days=7)) is ActivityDisplayStatus.active
        assert display_status(activity(status=ActivityStatus.ended), T0 + timedelta(days=30)) is ActivityDisplayStatus.ended

    def test_internal_only_hides_details_from_other_providers(self):
        a = activity(visibility=Visibility.internal_only)
        other = activity_view(a, "Agua Ya", "prov2", T0)
        own = activity_view(a, "Agua Ya", "prov1", T0)
        assert other.details_hidden and other.provider_name is None and other.schedule_description is None
        assert not own.details_hidden and own.provider_name == "Agua Ya"


class TestCoverage:
    def test_labels(self):
        reps = reporters_in("S1", 3) + reporters_in("S2", 3) + reporters_in("S3", 1)
        s = snap(reps)
        cov = {(c.area_id, c.category): c for c in compute_coverage(s.cells, [activity()], AREAS, END)}
        assert cov[("S1", W)].status is CoverageStatus.covered and cov[("S1", W)].activity_ids == ("act1",)
        assert cov[("S2", W)].status is CoverageStatus.uncovered
        assert cov[("S3", W)].status is CoverageStatus.unknown and cov[("S3", W)].reason == "suppressed"
        assert cov[("S4", W)].status is CoverageStatus.unknown and cov[("S4", W)].reason == "no_reports"
        assert cov[("S1", C)].status is CoverageStatus.unknown  # no data for charging

    def test_internal_only_counts_toward_coverage(self):
        s = snap(reporters_in("S1", 3))
        cov = compute_coverage(s.cells, [activity(visibility=Visibility.internal_only)], AREAS, END)
        assert next(c for c in cov if c.area_id == "S1" and c.category is W).status is CoverageStatus.covered

    @pytest.mark.parametrize("status", [ActivityStatus.planned, ActivityStatus.paused, ActivityStatus.ended])
    def test_only_active_activity_covers(self, status):
        s = snap(reporters_in("S1", 3))
        cov = compute_coverage(s.cells, [activity(status=status)], AREAS, END)
        assert next(c for c in cov if c.area_id == "S1" and c.category is W).status is CoverageStatus.uncovered

    def test_unconfirmed_activity_does_not_hide_gap_by_default(self):
        s = snap(reporters_in("S1", 3))
        late = END + timedelta(days=8)
        cov = compute_coverage(s.cells, [activity()], AREAS, late)
        assert next(c for c in cov if c.area_id == "S1" and c.category is W).status is CoverageStatus.uncovered
        cov2 = compute_coverage(s.cells, [activity()], AREAS, late, count_unconfirmed=True)
        assert next(c for c in cov2 if c.area_id == "S1" and c.category is W).status is CoverageStatus.covered

    def test_parish_activity_covers_sectors(self):
        s = snap(reporters_in("S2", 3))
        cov = compute_coverage(s.cells, [activity(area_ids=frozenset({"P1"}))], AREAS, END)
        assert next(c for c in cov if c.area_id == "S2" and c.category is W).status is CoverageStatus.covered

    def test_threshold(self):
        s = snap(reporters_in("S1", 3))
        cov = compute_coverage(s.cells, [], AREAS, END, threshold=5)
        c = next(c for c in cov if c.area_id == "S1" and c.category is W)
        assert c.status is CoverageStatus.unknown and c.reason == "need_at_or_below_threshold"

    def test_activity_never_changes_needs(self):
        reps = reporters_in("S1", 3)
        before = [r.needs for r in reps]
        compute_coverage(snap(reps).cells, [activity()], AREAS, END)
        assert [r.needs for r in reps] == before
        assert all(n.state is NeedState.active for r in reps for n in r.needs)


def perm(key, purpose=PermissionPurpose.contact_list, withdrawn=None):
    return Permission(key, purpose, "n1", T0 - timedelta(days=1), withdrawn)


class TestContactList:
    def setup_method(self):
        self.reps = [
            report(key="kA", area="S1", meeting_point="mp1", needs=[need(W, urgency=Urgency.urgent, preferred_times=("mañana",))]),
            report(key="kB", area="S2", needs=[need(W)]),  # no consent
            report(key="kC", area="S4", needs=[need(W)]),  # out of scope area
            report(key="kD", area="S1", needs=[need(C)]),  # out of scope category
            report(key="kE", area="S3", needs=[need(W, state=NeedState.stale)]),  # not active
            report(key="kF", area="S1", needs=[need(W)]),  # consent withdrawn
        ]
        self.contacts = {
            k: ReporterContact(k, phone_encrypted=f"enc-phone-{k}", alias=f"alias-{k}", name_encrypted=f"enc-name-{k}",
                               address_encrypted=f"enc-addr-{k}")
            for k in ("kA", "kB", "kC", "kD", "kE", "kF")
        }
        self.perms = [perm("kA"), perm("kC"), perm("kD"), perm("kE"), perm("kF", withdrawn=T0 - timedelta(hours=1)),
                      perm("kB", PermissionPurpose.refresh_prompts)]

    def run(self, profile, prov=None, c=None):
        return select_contact_list(c or ctx(Role.provider, provider="prov1", actor="pu1"), prov or provider(), profile,
                                   self.reps, self.contacts, self.perms, AREAS, T0)

    def test_only_consented_active_in_scope(self):
        rows, events = self.run(protective())
        assert [r.reporter_key for r in rows] == ["kA"]
        assert [(e.reporter_key, e.need_id, e.provider_id, e.actor_id) for e in events] == [
            ("kA", rows[0].need_id, "prov1", "pu1")
        ]

    def test_protective_fields(self):
        (row,), _ = self.run(protective())
        assert row.alias == "alias-kA" and row.sector_id == "S1" and row.meeting_point_id == "mp1"
        assert row.phone_encrypted == "enc-phone-kA"
        assert row.name_encrypted is None and row.address_encrypted is None
        assert row.urgency is Urgency.urgent and row.preferred_times == ("mañana",)

    def test_standard_fields(self):
        (row,), _ = self.run(standard())
        assert row.name_encrypted == "enc-name-kA" and row.address_encrypted == "enc-addr-kA"
        assert row.phone_encrypted == "enc-phone-kA"
        assert row.alias is None and row.meeting_point_id is None and row.sector_id is None

    @pytest.mark.parametrize("status", [VettingStatus.unvetted, VettingStatus.suspended])
    def test_unvetted_or_suspended_forbidden(self, status):
        with pytest.raises(Forbidden):
            self.run(protective(), prov=provider(vetting=status))

    def test_profile_disables_lists(self):
        with pytest.raises(Forbidden):
            self.run(protective(contact_list_enabled=False))

    def test_other_provider_users_forbidden(self):
        with pytest.raises(Forbidden):
            self.run(protective(), c=ctx(Role.provider, provider="prov2"))

    def test_withdrawal_immediate(self):
        self.perms = [perm("kA", withdrawn=T0)]
        rows, events = self.run(protective())
        assert rows == [] and events == []

    def test_contact_fields_subset(self):
        (row,), _ = self.run(protective(contact_list_fields=frozenset({ContactField.phone})))
        assert row.phone_encrypted and row.alias is None and row.sector_id is None


class TestAlerts:
    def subs(self, trigger, **kw):
        return AlertSubscription("sub1", "prov1", "pu1", frozenset({"S1", "S2"}), W, trigger, **kw)

    def evaluate(self, subs, current, previous=None, coverage=(), external=(), last=None, now=END, providers=None):
        return evaluate_alerts(subs, providers or {"prov1": provider()}, current, previous, coverage, external,
                               last or {}, now, AREAS)

    def test_new_urgent_needs(self):
        prev = snap(reporters_in("S1", 3))
        cur = snap(reporters_in("S1", 3) + reporters_in("S1", 2, urgency=Urgency.urgent, prefix="u"))
        (a,) = self.evaluate([self.subs(AlertTrigger.new_urgent_needs)], cur, prev)
        assert a.area_id == "S1" and a.value == 2 and a.trigger is AlertTrigger.new_urgent_needs

    def test_active_needs_above(self):
        cur = snap(reporters_in("S1", 5) + reporters_in("S2", 3))
        alerts = self.evaluate([self.subs(AlertTrigger.active_needs_above, threshold=4)], cur)
        assert [(a.area_id, a.value) for a in alerts] == [("S1", 5)]

    def test_area_uncovered(self):
        cur = snap(reporters_in("S2", 3))
        cov = compute_coverage(cur.cells, [], AREAS, END)
        (a,) = self.evaluate([self.subs(AlertTrigger.area_uncovered)], cur, coverage=cov)
        assert a.area_id == "S2"

    def test_external_outage(self):
        ext = [ExternalContext("P1", Service.piped_water, "monitor_ciudad", ServiceStatus.unavailable, END,
                               large_outage=True)]
        alerts = self.evaluate([self.subs(AlertTrigger.external_outage)], snap([]), external=ext)
        assert {a.area_id for a in alerts} == {"S1", "S2"} and alerts[0].source == "monitor_ciudad"

    def test_suppressed_cells_never_alert(self):
        cur = snap(reporters_in("S1", 2, urgency=Urgency.urgent))
        assert self.evaluate([self.subs(AlertTrigger.new_urgent_needs)], cur) == []
        assert self.evaluate([self.subs(AlertTrigger.active_needs_above, threshold=0)], cur) == []

    def test_dedup_window(self):
        cur = snap(reporters_in("S1", 5))
        s = self.subs(AlertTrigger.active_needs_above, threshold=1)
        (a,) = self.evaluate([s], cur)
        assert self.evaluate([s], cur, last={a.dedup_key: END}, now=END + timedelta(hours=5)) == []
        assert len(self.evaluate([s], cur, last={a.dedup_key: END}, now=END + timedelta(hours=6))) == 1

    def test_suspended_provider_gets_nothing(self):
        cur = snap(reporters_in("S1", 5))
        assert self.evaluate([self.subs(AlertTrigger.active_needs_above, threshold=1)], cur,
                             providers={"prov1": provider(vetting=VettingStatus.suspended)}) == []

    def test_alert_is_aggregate_only(self):
        fields = {f.name for f in dataclasses.fields(Alert)}
        forbidden = {"reporter_key", "report_id", "report_ids", "need_id", "phone", "phone_encrypted", "name",
                     "address", "alias", "meeting_point_id", "contact"}
        assert not fields & forbidden
        cur = snap(reporters_in("S1", 5))
        (a,) = self.evaluate([self.subs(AlertTrigger.active_needs_above, threshold=1)], cur)
        assert "kS1_" not in repr(a)  # no reporter keys leak
