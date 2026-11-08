"""DOM-030..033: privacy profiles as policy."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.domain.errors import PolicyBelowMinimum, ProfileViolation, ValidationFailed
from app.domain.profiles import (
    PLATFORM_MIN_K,
    PurgeField,
    capture_profile,
    loosened_settings,
    plan_tightening,
    protective_profile,
    run_purge,
    standard_profile,
    tightened_settings,
    validate_profile,
    validate_report_update,
    validate_submission,
)
from app.domain.types import (
    AddressLocation,
    AreaLevel,
    Channel,
    ContactField,
    GeoPoint,
    LocationMode,
    MeetingPointLocation,
    NeedCategory,
    NeedInput,
    PermissionPurpose,
    ProfileKind,
    Quantity,
    Relationship,
    ReporterContact,
    ReportSubmission,
    Unit,
)

from .factories import ORG, T0, protective, report, standard


def sub(**kw) -> ReportSubmission:
    base = dict(
        channel=Channel.whatsapp,
        relationship=Relationship.self,
        area_id="S1",
        questionnaire_version="q1",
        notice_version="n1",
    )
    base.update(kw)
    return ReportSubmission(**base)


class TestPlatformMinimums:
    def test_presets_are_valid(self):
        validate_profile(protective_profile(ORG))
        validate_profile(standard_profile(ORG))

    def test_protective_defaults_match_requirements(self):
        p = protective_profile(ORG)
        assert not p.names_allowed and not p.gps_allowed and not p.household_records_allowed
        assert p.location_mode is LocationMode.meeting_point
        assert p.reporter_phone_retention_days == 7
        assert p.contact_list_fields == {ContactField.alias, ContactField.sector, ContactField.meeting_point, ContactField.phone}
        assert not p.public_dashboard_enabled
        assert p.public_level is AreaLevel.parish and p.public_k >= 10 and p.public_delay >= timedelta(hours=24)

    def test_standard_defaults(self):
        p = standard_profile(ORG)
        assert p.contact_list_fields == {ContactField.name, ContactField.address, ContactField.phone}
        assert p.public_level is AreaLevel.sector and p.public_k == 5

    @pytest.mark.parametrize("k", [0, 1, 2])
    def test_aggregate_k_below_3_rejected(self, k):
        with pytest.raises(PolicyBelowMinimum):
            validate_profile(standard(aggregate_k=k))

    @pytest.mark.parametrize("k", [0, 2])
    def test_public_k_below_3_rejected(self, k):
        with pytest.raises(PolicyBelowMinimum):
            validate_profile(standard(public_k=k, aggregate_k=3))

    def test_public_k_must_not_be_finer_than_aggregate_k(self):
        with pytest.raises(PolicyBelowMinimum):
            validate_profile(standard(aggregate_k=6, public_k=5))

    def test_k_at_minimum_ok(self):
        validate_profile(standard(aggregate_k=PLATFORM_MIN_K, public_k=PLATFORM_MIN_K))

    def test_gps_requires_address_mode(self):
        with pytest.raises(PolicyBelowMinimum):
            validate_profile(standard(location_mode=LocationMode.meeting_point, gps_allowed=True,
                                      contact_list_fields=frozenset({ContactField.phone})))

    @pytest.mark.parametrize(
        "change",
        [
            {"public_k": 5},
            {"public_delay": timedelta(hours=1)},
            {"public_level": AreaLevel.sector},
            {"names_allowed": True},
            {"household_records_allowed": True},
        ],
    )
    def test_protective_floor(self, change):
        with pytest.raises(PolicyBelowMinimum):
            validate_profile(protective(**change))

    def test_custom_profile_can_adjust_within_minimums(self):
        p = replace(standard_profile(ORG), kind=ProfileKind.custom, aggregate_k=5, public_k=8, gps_allowed=False)
        assert validate_profile(p) is p


class TestCaptureValidation:
    @pytest.mark.parametrize(
        "kw,field",
        [
            ({"reporter_name_encrypted": "enc:Ana"}, "reporter_name"),
            ({"location": AddressLocation(address_encrypted="enc:calle")}, "location.address"),
            ({"location": AddressLocation(address_encrypted="enc", point=GeoPoint(10.5, -66.9))}, "location.point"),
            ({"household_ref": "hh1"}, "household_ref"),
        ],
    )
    def test_protective_rejects_personal_fields(self, kw, field):
        with pytest.raises(ProfileViolation) as e:
            validate_submission(sub(**kw), protective())
        assert field in e.value.fields
        assert e.value.code == "profile_violation"

    def test_protective_accepts_meeting_point(self):
        validate_submission(sub(location=MeetingPointLocation(meeting_point_id="mp1")), protective())
        validate_submission(sub(location=MeetingPointLocation(none_nearby=True)), protective())

    def test_standard_accepts_name_address_gps_household(self):
        validate_submission(
            sub(reporter_name_encrypted="enc", household_ref="hh",
                location=AddressLocation(address_encrypted="enc", point=GeoPoint(1, 2))),
            standard(),
        )

    def test_standard_without_gps_rejects_point_only(self):
        with pytest.raises(ProfileViolation) as e:
            validate_submission(sub(location=AddressLocation(address_encrypted="e", point=GeoPoint(1, 2))),
                                standard(gps_allowed=False))
        assert e.value.fields == ["location.point"]

    def test_area_report_never_stores_personal_data_even_in_standard(self):
        with pytest.raises(ProfileViolation):
            validate_submission(sub(relationship=Relationship.area, reporter_name_encrypted="x"), standard())

    def test_contact_permission_rejected_when_lists_disabled(self):
        with pytest.raises(ProfileViolation):
            validate_submission(sub(permissions=frozenset({PermissionPurpose.contact_list})),
                                protective(contact_list_enabled=False))

    @pytest.mark.parametrize(
        "category,unit,ok",
        [
            (NeedCategory.water_drinking, Unit.liters, True),
            (NeedCategory.water_other, Unit.liters, True),
            (NeedCategory.charging, Unit.devices, True),
            (NeedCategory.charging, Unit.liters, False),
            (NeedCategory.water_drinking, Unit.devices, False),
        ],
    )
    def test_units_per_category(self, category, unit, ok):
        s = sub(needs=(NeedInput(category, quantity=Quantity(Decimal("20"), unit)),))
        if ok:
            validate_submission(s, protective())
        else:
            with pytest.raises(ValidationFailed):
                validate_submission(s, protective())

    def test_negative_people_rejected(self):
        with pytest.raises(ValidationFailed):
            validate_submission(sub(needs=(NeedInput(NeedCategory.charging, people_affected=-1),)), protective())

    def test_duplicate_category_in_one_report_rejected(self):
        with pytest.raises(ValidationFailed):
            validate_submission(sub(needs=(NeedInput(NeedCategory.charging), NeedInput(NeedCategory.charging))),
                                protective())


class TestTightening:
    def test_standard_to_protective_purges_personal_fields(self):
        old, new = standard(version=1), protective(version=2, notice_version="n2")
        plan = plan_tightening(old, new, T0)
        assert plan.fields_to_purge >= {
            PurgeField.reporter_names,
            PurgeField.addresses,
            PurgeField.gps_points,
            PurgeField.household_records,
            PurgeField.reporter_phones,
        }
        assert plan.deadline == T0 + timedelta(hours=24)
        assert (plan.from_version, plan.to_version) == (1, 2)

    def test_gps_only_tightening(self):
        plan = plan_tightening(standard(), standard(version=2, gps_allowed=False), T0)
        assert plan.fields_to_purge == {PurgeField.gps_points}

    def test_no_change_no_purge(self):
        assert plan_tightening(standard(), standard(version=2), T0).empty

    def test_k_tightening_is_not_a_data_purge(self):
        plan = plan_tightening(standard(), standard(version=2, aggregate_k=5, public_k=6), T0)
        assert plan.empty
        assert "aggregate_k" in tightened_settings(standard(), standard(aggregate_k=5, public_k=6))

    def test_purge_run_redacts_and_counts(self):
        plan = plan_tightening(standard(), protective(version=2), T0)
        reps = [
            report(reporter_name_encrypted="enc", household="hh1"),
            replace(report(), location=AddressLocation(address_encrypted="enc", point=GeoPoint(1, 2))),
            report(),
        ]
        contacts = [ReporterContact("k1", phone_encrypted="p", name_encrypted="n", address_encrypted="a")]
        out, cts, audit = run_purge(plan, reps, contacts, now=T0 + timedelta(hours=3))
        for r in out:
            assert r.reporter_name_encrypted is None and r.household_ref is None
            assert not isinstance(r.location, AddressLocation)
        assert cts[0].name_encrypted is None and cts[0].address_encrypted is None
        assert cts[0].phone_encrypted == "p"  # phone handled by retention job
        assert audit.counts == {
            "reporter_names": 1,
            "household_records": 1,
            "addresses": 1,
            "gps_points": 1,
            "contact_names": 1,
            "contact_addresses": 1,
        }
        assert audit.within_deadline
        # audit holds counts only, no raw values
        assert "enc" not in repr(audit)

    def test_purge_after_deadline_flagged(self):
        plan = plan_tightening(standard(), protective(version=2), T0)
        _, _, audit = run_purge(plan, [], now=T0 + timedelta(hours=25))
        assert not audit.within_deadline

    def test_gps_only_purge_keeps_address(self):
        plan = plan_tightening(standard(), standard(version=2, gps_allowed=False), T0)
        r = replace(report(), location=AddressLocation(address_encrypted="enc", point=GeoPoint(1, 2)))
        (out,), _, audit = run_purge(plan, [r])
        assert out.location == AddressLocation(address_encrypted="enc", point=None)
        assert audit.counts == {"gps_points": 1}


class TestLoosening:
    def test_loosened_settings_detected(self):
        assert {"names_allowed", "location_mode", "gps_allowed"} <= loosened_settings(protective(), standard())

    def test_loosening_applies_only_under_new_notice(self):
        old = protective(version=1, notice_version="n1")
        new = standard(version=2, notice_version="n2")
        # Reporter acknowledged the new notice: standard capture.
        assert capture_profile(new, "n2", old).names_allowed
        # Reporter still on the old notice: captured as protective.
        eff = capture_profile(new, "n1", old)
        assert not eff.names_allowed and eff.location_mode is LocationMode.meeting_point and not eff.gps_allowed
        with pytest.raises(ProfileViolation):
            validate_submission(sub(reporter_name_encrypted="enc"), eff)

    def test_unknown_notice_is_most_restrictive(self):
        eff = capture_profile(standard(version=2, notice_version="n2"), "n-unknown", None)
        assert not eff.names_allowed and not eff.gps_allowed

    def test_existing_reports_never_enriched(self):
        collected_under = protective(version=1)
        active = standard(version=2, notice_version="n2")
        with pytest.raises(ProfileViolation):
            validate_report_update(sub(reporter_name_encrypted="enc"), collected_under, active)
        with pytest.raises(ProfileViolation):
            validate_report_update(sub(location=AddressLocation(address_encrypted="e")), collected_under, active)
        validate_report_update(sub(location=MeetingPointLocation("mp1")), collected_under, active)
