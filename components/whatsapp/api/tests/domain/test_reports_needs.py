"""DOM-010..023: reports, repeat reporters, corrections, need lifecycle."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.errors import InvalidTransition, ProfileViolation, ValidationFailed
from app.domain.indicators import compute_snapshot
from app.domain.needs import (
    NEED_TRANSITIONS,
    NeedActor,
    RefreshReply,
    apply_observation,
    apply_refresh_reply,
    tick_need,
    transition_need,
)
from app.domain.ports import SequentialIds
from app.domain.reports import (
    abandon_draft,
    confirm_report,
    correct_report,
    is_aggregatable,
    link_repeat,
    reporter_key,
    submit_report,
)
from app.domain.types import (
    AddressLocation,
    Bucket,
    Channel,
    Disposition,
    MeetingPointLocation,
    NeedCategory,
    NeedInput,
    NeedState,
    ObservationInput,
    PermissionPurpose,
    Relationship,
    ReportState,
    ReportSubmission,
    Role,
    Service,
    ServiceStatus,
    TimePrecision,
    Urgency,
)

from .factories import AREAS, ORG, T0, ctx, need, obs, protective, report, standard

SECRET = b"org-secret"


def sub(**kw) -> ReportSubmission:
    base = dict(
        channel=Channel.whatsapp,
        relationship=Relationship.self,
        area_id="S1",
        questionnaire_version="q1",
        notice_version="n1",
        location=MeetingPointLocation("mp1"),
        observations=(ObservationInput(Service.piped_water, ServiceStatus.unavailable, T0,
                                       outage_onset=T0 - timedelta(days=2), onset_precision=TimePrecision.day),),
        needs=(NeedInput(NeedCategory.water_drinking, stated_urgency=Urgency.urgent, people_affected=4),),
        permissions=frozenset({PermissionPurpose.notice_ack, PermissionPurpose.refresh_prompts}),
    )
    base.update(kw)
    return ReportSubmission(**base)


class TestReporterKey:
    def test_same_phone_same_key_within_period(self):
        a = reporter_key(SECRET, ORG, "+58 412-555-0101", T0, 30)
        b = reporter_key(SECRET, ORG, "584125550101", T0 + timedelta(hours=5), 30)
        assert a == b and a.startswith("rk_")
        assert "5550101" not in a

    def test_org_scoped(self):
        assert reporter_key(SECRET, ORG, "584125550101", T0, 30) != reporter_key(SECRET, "other", "584125550101", T0, 30)

    def test_rotates_per_profile_period(self):
        a = reporter_key(SECRET, ORG, "584125550101", T0, 1)
        b = reporter_key(SECRET, ORG, "584125550101", T0 + timedelta(days=2), 1)
        assert a != b

    def test_empty_endpoint_rejected(self):
        with pytest.raises(ValidationFailed):
            reporter_key(SECRET, ORG, "abc", T0, 30)


class TestSubmit:
    def test_submit_creates_draft_with_profile_version_and_observation_semantics(self):
        r = submit_report(ctx(), sub(), protective(version=4), T0, SequentialIds(), reporter_key="rk1")
        assert r.state is ReportState.draft and r.confirmed_at is None
        assert r.profile_version == 4 and r.notice_version == "n1" and r.questionnaire_version == "q1"
        (o,) = r.observations
        assert o.observed_at == T0 and o.outage_onset == T0 - timedelta(days=2)
        assert o.onset_precision is TimePrecision.day
        (n,) = r.needs
        assert n.state is NeedState.active and n.stated_urgency is Urgency.urgent and n.people_affected == 4
        assert not is_aggregatable(r)

    def test_protective_rejects_name(self):
        with pytest.raises(ProfileViolation):
            submit_report(ctx(), sub(reporter_name_encrypted="enc"), protective(), T0, SequentialIds())

    def test_area_only_report_stores_no_personal_data(self):
        r = submit_report(
            ctx(),
            sub(relationship=Relationship.area, needs=(),
                permissions=frozenset({PermissionPurpose.notice_ack, PermissionPurpose.refresh_prompts,
                                       PermissionPurpose.contact_list})),
            standard(), T0, SequentialIds(),
        )
        assert r.reporter_name_encrypted is None and r.household_ref is None
        assert not isinstance(r.location, AddressLocation)
        assert r.permissions == {PermissionPurpose.notice_ack}

    def test_profile_of_other_org_rejected(self):
        with pytest.raises(ValidationFailed):
            submit_report(ctx(org="x"), sub(), protective(), T0, SequentialIds())

    def test_unknown_status_kept_distinct(self):
        r = submit_report(ctx(), sub(observations=(ObservationInput(Service.electricity, ServiceStatus.unknown, T0),)),
                          protective(), T0, SequentialIds())
        assert r.observations[0].status is ServiceStatus.unknown


class TestDraftConfirm:
    def test_only_confirmed_reports_aggregate(self):
        ids = SequentialIds()
        d = submit_report(ctx(), sub(), protective(), T0, ids, reporter_key="rk1")
        assert not is_aggregatable(d)
        c = confirm_report(d, T0 + timedelta(minutes=2))
        assert c.state is ReportState.confirmed and c.confirmed_at == T0 + timedelta(minutes=2)
        assert is_aggregatable(c)

    def test_abandoned_draft_contributes_nothing(self):
        d = submit_report(ctx(), sub(), protective(), T0, SequentialIds(), reporter_key="rk1")
        a = abandon_draft(d)
        assert a.state is ReportState.abandoned and not is_aggregatable(a)
        snap = compute_snapshot(ORG, [a, d], AREAS, protective(), Bucket.h24, T0 + timedelta(hours=1), T0)
        assert all(c.distinct_reporters is None for c in snap.cells)

    @pytest.mark.parametrize("state", [ReportState.confirmed, ReportState.abandoned])
    def test_cannot_confirm_twice_or_after_abandon(self, state):
        with pytest.raises(InvalidTransition):
            confirm_report(report(state=state), T0)


class TestCorrections:
    def test_correction_supersedes_and_keeps_prior(self):
        ids = SequentialIds()
        prior = confirm_report(submit_report(ctx(), sub(), protective(), T0, ids, reporter_key="rk1"), T0)
        later = T0 + timedelta(hours=1)
        old, new = correct_report(
            ctx(), prior,
            sub(needs=(NeedInput(NeedCategory.water_drinking, stated_urgency=Urgency.soon, people_affected=6),)),
            protective(), later, ids,
        )
        assert old.state is ReportState.superseded and old.superseded_by_id == new.id
        assert new.supersedes_id == prior.id and new.state is ReportState.confirmed
        assert not is_aggregatable(old) and is_aggregatable(new)
        assert new.reporter_key == "rk1"
        assert new.needs[0].linked_need_id == prior.needs[0].id
        assert new.needs[0].created_at == prior.needs[0].created_at  # need age preserved
        snap = compute_snapshot(ORG, [old, new], AREAS, protective(aggregate_k=3), Bucket.h24, T0 + timedelta(hours=2), later)
        # Only the latest version would count (one reporter -> thin here)
        cell = next(c for c in snap.cells if c.area_id == "S1" and c.subject is NeedCategory.water_drinking)
        assert cell.coverage.value == "thin"

    def test_cannot_correct_a_draft(self):
        d = submit_report(ctx(), sub(), protective(), T0, SequentialIds())
        with pytest.raises(InvalidTransition):
            correct_report(ctx(), d, sub(), protective(), T0, SequentialIds())

    def test_correction_keeps_human_exclusion(self):
        prior = report(key="rk", disposition=Disposition.spam, exclusion_reason="bot")
        _, new = correct_report(ctx(), prior, sub(), protective(), T0, SequentialIds())
        assert not is_aggregatable(new)


class TestRepeatReporters:
    def test_repeat_report_replaces_open_need_of_same_category(self):
        first = report(key="rk1", needs=[need(NeedCategory.water_drinking, at=T0)])
        second = report(key="rk1", at=T0 + timedelta(hours=3),
                        needs=[need(NeedCategory.water_drinking, at=T0 + timedelta(hours=3)),
                               need(NeedCategory.charging, at=T0 + timedelta(hours=3))])
        linked, replaced = link_repeat(second, [first], T0 + timedelta(hours=3))
        assert [n.replaced_by_id for n in replaced] == [linked.needs[0].id]
        assert not replaced[0].is_open
        assert linked.needs[0].linked_need_id == first.needs[0].id
        assert linked.needs[0].created_at == T0
        assert linked.needs[1].linked_need_id is None

    def test_no_key_no_link(self):
        r = report(key=None, needs=[need()])
        assert link_repeat(r, [report(key=None, needs=[need()])], T0) == (r, [])

    def test_same_phone_three_times_counts_once(self):
        """DOM-014 accept: three "no water" reports in a day = one reporter."""
        reps = [
            report(key="rkA", at=T0 + timedelta(hours=h),
                   observations=[obs(Service.piped_water, ServiceStatus.unavailable, T0 + timedelta(hours=h))],
                   needs=[need(at=T0 + timedelta(hours=h))])
            for h in (0, 4, 8)
        ]
        others = [report(key=f"rk{i}", needs=[need()]) for i in range(2)]
        snap = compute_snapshot(ORG, reps + others, AREAS, protective(), Bucket.h24, T0 + timedelta(hours=12),
                                T0 + timedelta(hours=12))
        cell = next(c for c in snap.cells if c.area_id == "S1" and c.subject is NeedCategory.water_drinking)
        assert cell.distinct_reporters == 3
        assert cell.active_needs == 3
        svc = next(c for c in snap.cells if c.area_id == "S1" and c.subject is Service.piped_water)
        assert svc.coverage.value == "thin"  # one distinct reporter, not three


class TestNeedLifecycle:
    def test_goes_stale_after_72h_and_expires_after_14d(self):
        n = need(at=T0)
        assert tick_need(n, T0 + timedelta(hours=71)).state is NeedState.active
        s = tick_need(n, T0 + timedelta(hours=72))
        assert s.state is NeedState.stale
        assert tick_need(s, T0 + timedelta(days=13)).state is NeedState.stale
        assert tick_need(s, T0 + timedelta(days=14)).state is NeedState.expired
        assert tick_need(n, T0 + timedelta(days=15)).state is NeedState.expired

    def test_refresh_yes_reactivates(self):
        s = tick_need(need(at=T0), T0 + timedelta(hours=80))
        later = T0 + timedelta(hours=81)
        a, _ = apply_refresh_reply(s, RefreshReply(still_needs=True), later)
        assert a.state is NeedState.active and a.last_confirmed_at == later
        assert tick_need(a, later + timedelta(hours=71)).state is NeedState.active

    def test_refresh_no_resolves(self):
        a, _ = apply_refresh_reply(need(), RefreshReply(still_needs=False), T0)
        assert a.state is NeedState.resolved_by_reporter

    def test_withdraw(self):
        a, _ = apply_refresh_reply(need(), RefreshReply(withdraw=True), T0)
        assert a.state is NeedState.withdrawn

    def test_service_restored_never_resolves(self):
        n = need()
        a, o = apply_refresh_reply(n, RefreshReply(service=Service.piped_water,
                                                   service_status=ServiceStatus.available), T0)
        assert a.state is NeedState.active
        assert o is not None and o.status is ServiceStatus.available
        a2, _ = apply_refresh_reply(n, RefreshReply(still_needs=True, service=Service.piped_water,
                                                    service_status=ServiceStatus.available), T0)
        assert a2.state is NeedState.active
        assert apply_observation(n, o) is n

    @pytest.mark.parametrize("final", [NeedState.resolved_by_reporter, NeedState.withdrawn, NeedState.expired])
    def test_terminal_states_are_terminal(self, final):
        n = need(state=final)
        for to in NeedState:
            with pytest.raises(InvalidTransition):
                transition_need(n, to, NeedActor.reporter, T0)
        assert tick_need(n, T0 + timedelta(days=30)) is n
        assert apply_refresh_reply(n, RefreshReply(still_needs=True), T0)[0] is n

    @pytest.mark.parametrize("actor", [NeedActor.provider, NeedActor.staff])
    @pytest.mark.parametrize("to", list(NeedState))
    def test_providers_and_staff_never_change_needs(self, actor, to):
        """DOM-022: no dispatch semantics."""
        for start in (NeedState.active, NeedState.stale):
            with pytest.raises(InvalidTransition):
                transition_need(need(state=start), to, actor, T0)

    def test_reporter_cannot_expire_and_system_cannot_resolve(self):
        with pytest.raises(InvalidTransition):
            transition_need(need(), NeedState.expired, NeedActor.reporter, T0)
        with pytest.raises(InvalidTransition):
            transition_need(need(), NeedState.resolved_by_reporter, NeedActor.system, T0)

    def test_transition_table_has_no_provider_or_staff_entries(self):
        for actors in NEED_TRANSITIONS.values():
            assert NeedActor.provider not in actors and NeedActor.staff not in actors

    def test_urgency_stored_as_reported(self):
        """DOM-023: urgent flag by staff does not change stated urgency."""
        from app.domain.review import flag_urgent

        r = report(key="k", needs=[need(urgency=Urgency.can_wait)])
        flagged, task = flag_urgent(r, SequentialIds(), T0)
        assert flagged.needs[0].stated_urgency is Urgency.can_wait
        assert flagged.urgent_flagged and is_aggregatable(flagged)
