"""DOM-060..064: permissions, outbound gate, refresh prompts, broadcasts, opt-out."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.communication import (
    BroadcastTemplate,
    approve_broadcast,
    check_gate,
    gate_batch,
    grant_permission,
    process_optout,
    record_prompt_sent,
    refresh_due,
    schedule_refresh_prompts,
    select_broadcast_recipients,
    withdraw_permission,
)
from app.domain.errors import Forbidden, ValidationFailed
from app.domain.types import (
    Activity,
    ActivityStatus,
    ActivityType,
    GateBlockReason,
    NeedCategory,
    NeedState,
    OutboundIntent,
    OutboundPurpose,
    PermissionPurpose,
    ProviderOrganization,
    ReporterCommState,
    Role,
    Schedule,
    SentMessage,
    VettingStatus,
)

from .factories import AREAS, ORG, T0, ctx, need, report

P = PermissionPurpose
O = OutboundPurpose


def perms(key="k", *purposes, at=T0 - timedelta(days=5)):
    return [grant_permission(key, p, "n1", at) for p in purposes]


def intent(purpose, key="k", template="tpl", at=T0):
    return OutboundIntent(key, purpose, at, template_id=template)


class TestPermissions:
    def test_records_purpose_notice_and_time(self):
        p = grant_permission("k", P.area_broadcasts, "n3", T0)
        assert (p.purpose, p.notice_version, p.granted_at) == (P.area_broadcasts, "n3", T0)
        assert p.active_at(T0) and not p.active_at(T0 - timedelta(seconds=1))

    def test_withdraw_is_immediate_and_idempotent(self):
        p = withdraw_permission(grant_permission("k", P.refresh_prompts, "n1", T0), T0 + timedelta(hours=1))
        assert not p.active_at(T0 + timedelta(hours=1)) and p.active_at(T0 + timedelta(minutes=59))
        assert withdraw_permission(p, T0 + timedelta(days=1)) == p


class TestGate:
    state = ReporterCommState("k", last_inbound_at=T0 - timedelta(hours=1))

    def test_allowed(self):
        assert check_gate(intent(O.refresh_prompt), perms("k", P.refresh_prompts), self.state, [], T0).allowed

    def test_needs_purpose_permission(self):
        r = check_gate(intent(O.refresh_prompt), perms("k", P.area_broadcasts), self.state, [], T0)
        assert r.reason is GateBlockReason.no_permission
        r = check_gate(intent(O.area_broadcast), perms("k", P.refresh_prompts), self.state, [], T0)
        assert r.reason is GateBlockReason.no_permission

    def test_withdrawn_single_purpose_stops_only_that_purpose(self):
        ps = perms("k", P.refresh_prompts, P.area_broadcasts)
        ps[0] = withdraw_permission(ps[0], T0 - timedelta(minutes=1))
        assert not check_gate(intent(O.refresh_prompt), ps, self.state, [], T0).allowed
        assert check_gate(intent(O.area_broadcast), ps, self.state, [], T0).allowed

    def test_optout_blocks_everything_but_confirmation(self):
        st = ReporterCommState("k", opted_out_at=T0 - timedelta(minutes=1), last_inbound_at=T0 - timedelta(minutes=1))
        ps = perms("k", *P)
        for purpose in (O.refresh_prompt, O.area_broadcast, O.conversation_reply):
            assert check_gate(intent(purpose), ps, st, [], T0).reason is GateBlockReason.opted_out
        assert check_gate(intent(O.optout_confirmation, template=None), ps, st, [], T0).allowed

    def test_window_or_template(self):
        out = ReporterCommState("k", last_inbound_at=T0 - timedelta(hours=25))
        r = check_gate(intent(O.conversation_reply, template=None), [], out, [], T0)
        assert r.reason is GateBlockReason.outside_window_no_template
        assert check_gate(intent(O.conversation_reply, template=None), [], self.state, [], T0).allowed
        assert check_gate(intent(O.refresh_prompt, template="tpl"), perms("k", P.refresh_prompts), out, [], T0).allowed
        never = ReporterCommState("k")
        assert not check_gate(intent(O.conversation_reply, template=None), [], never, [], T0).allowed

    def test_daily_rate_limit(self):
        sent = [SentMessage("k", O.refresh_prompt, T0 - timedelta(hours=h)) for h in (1, 2, 3)]
        r = check_gate(intent(O.refresh_prompt), perms("k", P.refresh_prompts), self.state, sent, T0)
        assert r.reason is GateBlockReason.rate_limited
        # replies inside the conversation are not rate-limited
        assert check_gate(intent(O.conversation_reply), [], self.state, sent, T0).allowed

    def test_weekly_broadcast_cap(self):
        sent = [SentMessage("k", O.area_broadcast, T0 - timedelta(days=d)) for d in (2, 5)]
        ps = perms("k", P.area_broadcasts)
        assert check_gate(intent(O.area_broadcast), ps, self.state, sent, T0).reason is GateBlockReason.rate_limited
        assert check_gate(intent(O.area_broadcast), ps, self.state, sent, T0 + timedelta(days=3)).allowed

    def test_mismatched_state_rejected(self):
        with pytest.raises(ValidationFailed):
            check_gate(intent(O.refresh_prompt, key="x"), [], self.state, [], T0)

    def test_batch_counts_blocked_and_applies_limits_in_batch(self):
        ps = perms("a", P.area_broadcasts) + perms("b", P.refresh_prompts)
        states = {"a": ReporterCommState("a", last_inbound_at=T0), "b": ReporterCommState("b", opted_out_at=T0)}
        intents = [intent(O.area_broadcast, "a"), intent(O.area_broadcast, "a"), intent(O.area_broadcast, "a"),
                   intent(O.refresh_prompt, "b"), intent(O.refresh_prompt, "c")]
        res = gate_batch(intents, ps, states, [], T0)
        assert len(res.allowed) == 2
        assert res.blocked_counts == {GateBlockReason.rate_limited: 1, GateBlockReason.opted_out: 1,
                                      GateBlockReason.no_permission: 1}
        assert not hasattr(res, "tasks")  # blocked intents create no staff tasks


class TestOptOut:
    def test_baja(self):
        ps = perms("k", P.refresh_prompts, P.area_broadcasts, P.contact_list)
        st, withdrawn, confirm = process_optout(ReporterCommState("k"), ps + perms("other", P.refresh_prompts), T0)
        assert st.opted_out_at == T0
        assert len(withdrawn) == 3 and all(not p.active_at(T0) for p in withdrawn)
        assert confirm.purpose is O.optout_confirmation
        assert check_gate(confirm, withdrawn, st, [], T0).allowed


class TestRefreshPrompts:
    def test_due_every_72h_max_3(self):
        n = need(at=T0)
        assert not refresh_due(n, T0 + timedelta(hours=71))
        assert refresh_due(n, T0 + timedelta(hours=72))
        n1 = record_prompt_sent(n, T0 + timedelta(hours=72))
        assert not refresh_due(n1, T0 + timedelta(hours=100))
        assert refresh_due(n1, T0 + timedelta(hours=144))
        n3 = record_prompt_sent(record_prompt_sent(n1, T0 + timedelta(hours=144)), T0 + timedelta(hours=216))
        assert n3.refresh_prompts_sent == 3
        assert not refresh_due(n3, T0 + timedelta(days=30))

    @pytest.mark.parametrize("state,due", [(NeedState.active, True), (NeedState.stale, True),
                                           (NeedState.resolved_by_reporter, False), (NeedState.withdrawn, False),
                                           (NeedState.expired, False)])
    def test_only_active_or_stale(self, state, due):
        assert refresh_due(need(state=state, at=T0), T0 + timedelta(days=4)) is due

    def test_schedule_respects_permission_and_optout(self):
        reps = [report(key=k, needs=[need(NeedCategory.charging, at=T0)]) for k in ("a", "b", "c")]
        ps = perms("a", P.refresh_prompts) + perms("b", P.refresh_prompts)
        states = {"b": ReporterCommState("b", opted_out_at=T0)}
        out = schedule_refresh_prompts(reps, ps, states, T0 + timedelta(hours=73))
        assert [(i.reporter_key, i.need_id, i.purpose) for i in out] == [("a", reps[0].needs[0].id, O.refresh_prompt)]
        assert out[0].template_id is not None

    def test_replaced_need_not_prompted(self):
        r = report(key="a", needs=[need(at=T0, replaced_by_id="newer")])
        assert schedule_refresh_prompts([r], perms("a", P.refresh_prompts), {}, T0 + timedelta(days=4)) == []


def act(**kw):
    base = dict(id="act1", provider_id="prov1", type=ActivityType.water_distribution_point,
                category=NeedCategory.water_drinking, area_ids=frozenset({"S1"}), schedule=Schedule(True, "sáb 8–12"),
                status=ActivityStatus.active, last_confirmed_at=T0)
    base.update(kw)
    return Activity(**base)


def prov(**kw):
    base = dict(id="prov1", org_id=ORG, name="Agua Ya", vetting=VettingStatus.vetted,
                scope_area_ids=frozenset({"P1"}), scope_categories=frozenset({NeedCategory.water_drinking}))
    base.update(kw)
    return ProviderOrganization(**base)


TPL = BroadcastTemplate("bt1", "Punto de agua en {lugar}, {horario}, organizado por {organizacion}",
                        "Punto de agua en {lugar}, {horario}")


class TestBroadcasts:
    def test_provider_name_only_if_allowed(self):
        a = approve_broadcast(ctx(Role.coordinator), "b1", TPL, act(), prov(name_in_broadcasts_allowed=True),
                              "Plaza X", T0)
        assert a.text == "Punto de agua en Plaza X, sáb 8–12, organizado por Agua Ya" and a.approved_by == "user_1"
        b = approve_broadcast(ctx(Role.coordinator), "b2", TPL, act(), prov(), "Plaza X", T0)
        assert "Agua Ya" not in b.text

    def test_only_coordinator_approves(self):
        with pytest.raises(Forbidden):
            approve_broadcast(ctx(Role.provider), "b", TPL, act(), prov(), "Plaza", T0)

    def test_ended_activity_rejected(self):
        with pytest.raises(ValidationFailed):
            approve_broadcast(ctx(Role.coordinator), "b", TPL, act(status=ActivityStatus.ended), prov(), "P", T0)

    def test_bad_template_rejected(self):
        bad = BroadcastTemplate("x", "{desconocido}", "{desconocido}")
        with pytest.raises(ValidationFailed):
            approve_broadcast(ctx(Role.coordinator), "b", bad, act(), prov(), "P", T0)

    def test_recipients(self):
        reps = [
            report(key="a", area="S1", needs=[need(NeedCategory.water_drinking)]),
            report(key="b", area="S1", needs=[need(NeedCategory.charging)]),  # wrong category
            report(key="c", area="S2", needs=[need(NeedCategory.water_drinking)]),  # outside areas
            report(key="d", area="S1", needs=[need(NeedCategory.water_drinking)]),  # no permission
            report(key="e", area="S1", needs=[need(NeedCategory.water_drinking)]),  # weekly cap
            report(key="f", area="S1", needs=[need(NeedCategory.water_drinking)]),  # opted out
            report(key="g", area="S1", needs=[need(NeedCategory.water_drinking, state=NeedState.stale)]),  # not active
        ]
        ps = sum((perms(k, P.area_broadcasts) for k in "abcefg"), [])
        sent = [SentMessage("e", O.area_broadcast, T0 - timedelta(days=d)) for d in (1, 3)]
        states = {"f": ReporterCommState("f", opted_out_at=T0 - timedelta(days=1))}
        assert select_broadcast_recipients(act(), reps, ps, states, sent, AREAS, T0) == ["a"]
