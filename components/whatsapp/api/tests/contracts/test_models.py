"""Model rules that fixtures alone don't cover (CON-003, CON-004, CON-016, CON-040)."""
from __future__ import annotations

import copy
import inspect
import typing
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.contracts import (
    admin,
    aggregation,
    base,
    data_jobs,
    errors,
    events,
    jobs,
    providers,
    public,
    questionnaires,
    reports,
)
from app.contracts.base import ContractModel, to_wire

from ._util import FIXTURES_DIR, load

SUBMISSION = load(FIXTURES_DIR / "valid/report_submission/protective_meeting_point.json")
QUESTIONNAIRE = load(FIXTURES_DIR / "valid/questionnaire_definition/csl_report_v1.json")
DATA_JOB = load(FIXTURES_DIR / "valid/data_job_request/monitor_ciudad.json")


def _models(module) -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(module).values()
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == module.__name__
    ]


def _nested_models(model: type[BaseModel], seen=None) -> set[type[BaseModel]]:
    seen = seen if seen is not None else set()
    if model in seen:
        return seen
    seen.add(model)
    for field in model.model_fields.values():
        for arg in _flatten(field.annotation):
            if inspect.isclass(arg) and issubclass(arg, BaseModel):
                _nested_models(arg, seen)
    return seen


def _flatten(tp):
    yield tp
    for arg in typing.get_args(tp):
        yield from _flatten(arg)


V1_MODULES = [admin, aggregation, data_jobs, errors, events, jobs, providers, public, questionnaires, reports]


# ---- strictness (CON-005) ---------------------------------------------------


@pytest.mark.parametrize("module", V1_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[1])
def test_all_v1_models_are_strict_and_closed(module):
    for model in _models(module):
        assert issubclass(model, ContractModel), model
        assert model.model_config.get("strict") is True, model
        assert model.model_config.get("extra") == "forbid", model


def test_no_silent_coercion_on_python_input():
    for path, bad in [
        (("needs", 0, "people_affected"), "4"),
        (("needs", 0, "people_affected"), 4.0),
        (("needs", 0, "people_affected"), True),
        (("permissions", 0, "notice_version"), "1"),
    ]:
        data = copy.deepcopy(SUBMISSION)
        cur = data
        for p in path[:-1]:
            cur = cur[p]
        cur[path[-1]] = bad
        with pytest.raises(ValidationError):
            reports.ReportSubmission.model_validate(data)


def test_nan_and_infinity_rejected():
    data = copy.deepcopy(SUBMISSION)
    data["needs"][0]["quantity"]["value"] = float("nan")
    with pytest.raises(ValidationError):
        reports.ReportSubmission.model_validate(data)
    with pytest.raises(ValidationError):
        base.Quantity.model_validate_json('{"value": NaN, "unit": "liters"}')
    with pytest.raises(ValidationError):
        base.Quantity.model_validate_json('{"value": Infinity, "unit": "liters"}')


# ---- time and identifiers (CON-002) ---------------------------------------


def test_utc_instant_normalizes_and_serializes_with_z():
    class M(ContractModel):
        at: base.UtcInstant

    m = M.model_validate({"at": "2026-11-07T10:00:00.5+00:00"})
    assert m.at.tzinfo is not None and m.at.utcoffset() == timedelta(0)
    assert to_wire(m) == {"at": "2026-11-07T10:00:00.500000Z"}
    assert M(at=datetime(2026, 11, 7, tzinfo=timezone.utc)).at.tzinfo == timezone.utc
    with pytest.raises(ValidationError):
        M(at=datetime(2026, 11, 7))  # naive
    with pytest.raises(ValidationError):
        M(at=datetime(2026, 11, 7, tzinfo=timezone(timedelta(hours=-4))))


def test_local_timezone_must_exist():
    class M(ContractModel):
        tz: base.LocalTimezone

    assert M.model_validate({"tz": "America/Caracas"}).tz == "America/Caracas"
    with pytest.raises(ValidationError):
        M.model_validate({"tz": "America/Atlantis"})


# ---- unknown vs absent (CON-003) ------------------------------------------


def test_not_asked_stays_omitted_on_the_wire():
    need = reports.NeedDetail.model_validate({"category": "charging", "stated_urgency": "unknown"})
    assert to_wire(need) == {"category": "charging", "stated_urgency": "unknown"}
    asked = reports.NeedDetail.model_validate(
        {"category": "charging", "stated_urgency": "unknown", "quantity": "unknown", "people_affected": 0}
    )
    assert to_wire(asked)["quantity"] == "unknown"
    assert to_wire(asked)["people_affected"] == 0


def test_not_asked_rejects_explicit_null():
    with pytest.raises(ValidationError):
        reports.NeedDetail.model_validate({"category": "charging", "stated_urgency": "low", "people_affected": None})


def test_reported_time_unknown_has_no_instant():
    assert reports.ReportedTime.model_validate({"precision": "unknown"}).at is None
    with pytest.raises(ValidationError):
        reports.ReportedTime.model_validate({"precision": "approximate"})


def test_outage_onset_only_for_outage_status():
    obs = {"service": "electricity", "status": "available", "observed_at": {"precision": "unknown"},
           "outage_since": {"precision": "unknown"}}
    with pytest.raises(ValidationError):
        reports.Observation.model_validate(obs)


# ---- privacy (CON-004, CON-015, CON-016) -----------------------------------

PERSONAL_FIELDS = {"name", "phone", "address", "address_text", "point", "lat", "lon", "sender", "recipient",
                   "landmark", "alias", "email", "responsible_contact_email", "responsible_contact_name"}

# Models allowed to carry personal fields, and why.
PERSONAL_ALLOWED = {
    reports.AddressLocation, reports.GeoPoint,  # standard-profile staff detail only
    providers.ProtectiveContactRow, providers.StandardContactRow, providers._ContactRowCommon,
    providers.ProviderOrganization,  # the provider's own responsible contact, not a resident
    events.InboundMessage, events.DeliveryStatusEvent, events.LocationContent,  # restricted events
    # Public place names, not people:
    providers.PublicSite, providers.ContactMeetingPoint, public.PublicArea, public.PublicMeetingPoint,
    public.PublicSiteLocation, admin.MeetingPoint, admin.MeetingPointInput, admin.CampaignConfig,
    providers.ApiKey, providers.ApiKeyInput, providers.Activity,  # key label; provider org name
}


@pytest.mark.parametrize(
    "root",
    [aggregation.IndicatorCell, aggregation.AreaOfNeed, aggregation.CoverageCell, providers.Alert,
     providers.AlertSubscription, providers.Activity, providers.ApiKey, public.PublicIndicatorCell,
     public.PublicActivity, admin.Broadcast, admin.ReviewTask, *jobs.JOB_MODELS, data_jobs.DataJobResult],
    ids=lambda m: m.__name__,
)
def test_aggregate_provider_public_models_have_no_personal_fields(root):
    for model in _nested_models(root):
        if model in PERSONAL_ALLOWED and model not in (providers.Activity, providers.ApiKey):
            continue
        leaked = PERSONAL_FIELDS & set(model.model_fields)
        if model is providers.Activity:
            leaked -= {"provider_name"}
        if model is providers.ApiKey:
            leaked -= {"name"}  # the key's label
        assert not leaked, f"{model.__name__} exposes {leaked}"


def test_public_models_are_standalone():
    internal = {m for mod in V1_MODULES if mod is not public for m in _models(mod)}
    for model in _models(public):
        bases = [b for b in model.__mro__[1:] if issubclass(b, BaseModel)]
        assert bases[0] is ContractModel, f"{model.__name__} subclasses {bases[0].__name__}"
        assert not (set(model.__mro__) & internal)
        for nested in _nested_models(model):
            assert nested.__module__ in (public.__name__,), f"{model.__name__} nests internal {nested.__name__}"


def test_contact_rows_are_disjoint_by_profile():
    prot = set(providers.ProtectiveContactRow.model_fields)
    std = set(providers.StandardContactRow.model_fields)
    assert {"alias", "meeting_point"} <= prot and not ({"name", "address"} & prot)
    assert {"name", "address"} <= std and not ({"alias", "meeting_point"} & std)


def test_api_key_secret_only_in_created():
    assert "secret" not in providers.ApiKey.model_fields
    assert "secret" in providers.ApiKeyCreated.model_fields


def test_profile_location_rule():
    profile = admin.PrivacyProfile.model_validate(load(FIXTURES_DIR / "valid/privacy_profile/csl_protective.json"))
    assert profile.settings.allows_location("meeting_point")
    assert not profile.settings.allows_location("address")
    assert admin.PLATFORM_MINIMUMS.aggregate_k == admin.PLATFORM_MIN_K == 3


def test_public_band_for():
    assert [public.band_for(n) for n in (0, 1, 9, 10, 24, 25, 249, 250, 10_000)] == [
        "0", "1-9", "1-9", "10-24", "10-24", "25-49", "100-249", "250+", "250+"]
    assert set(typing.get_args(public.CountBand)) == {b for _, _, b in public.BAND_EDGES}


# ---- Pydantic-only semantic rules (not expressible in JSON Schema) ----------


def test_data_job_window_order_and_bound():
    bad = {**DATA_JOB, "observation_window_end": DATA_JOB["observation_window_start"]}
    with pytest.raises(ValidationError):
        data_jobs.DataJobRequest.model_validate(bad)
    long = {**DATA_JOB, "observation_window_start": "2026-01-01T00:00:00Z"}
    with pytest.raises(ValidationError, match="92 days"):
        data_jobs.DataJobRequest.model_validate(long)


def test_data_job_units_cover_every_indicator():
    assert set(data_jobs.INDICATOR_UNIT) == set(typing.get_args(data_jobs.IndicatorType))


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda q: q["steps"].append(copy.deepcopy(q["steps"][0])), "unique"),
        (lambda q: q.update(start="nowhere"), "start"),
        (lambda q: q["steps"][0].update(next="missing"), "unknown step"),
        (lambda q: q["steps"][0].update(maps_to="household.members"), "stable report field"),
        (lambda q: q["steps"][1]["branches"][0]["when"][0].update(step_id="ghost"), "unknown step"),
        (lambda q: q["steps"][1]["branches"][0]["when"][0].update(op="is_unknown"), "takes no values"),
    ],
)
def test_questionnaire_graph_rules(mutate, message):
    q = copy.deepcopy(QUESTIONNAIRE)
    mutate(q)
    with pytest.raises(ValidationError, match=message):
        questionnaires.QuestionnaireDefinition.model_validate(q)


def test_questionnaire_maps_only_to_stable_fields():
    q = questionnaires.QuestionnaireDefinition.model_validate(QUESTIONNAIRE)
    assert q.ref == questionnaires.QuestionnaireRef(key="csl_report", version=1)
    assert all(s.maps_to in questionnaires.MAPPABLE_FIELDS for s in q.steps)


def test_need_quantity_units_follow_category():
    assert set(reports.NEED_QUANTITY_UNIT) == set(typing.get_args(base.NeedCategory))
    assert set(providers.ACTIVITY_CAPACITY_UNIT) == set(typing.get_args(base.NeedCategory))


def test_draft_accepts_nothing_and_submission_requires_core_fields():
    assert to_wire(reports.ReportDraft.model_validate({})) == {}
    with pytest.raises(ValidationError):
        reports.ReportSubmission.model_validate({})


# ---- error envelope (CON-040) ----------------------------------------------


def test_error_codes_complete():
    expected = {"validation_failed", "not_found", "forbidden", "conflict", "stale_version", "invalid_transition",
                "idempotency_conflict", "rate_limited", "unsupported_version", "profile_violation"}
    assert set(typing.get_args(errors.ErrorCode)) == expected == set(errors.HTTP_STATUS)


def test_validation_error_maps_to_envelope_without_input():
    data = copy.deepcopy(SUBMISSION)
    data["needs"][1]["quantity"] = {"value": 3, "unit": "gallons"}
    data["reporter_name"] = "María"
    with pytest.raises(ValidationError) as info:
        reports.ReportSubmission.model_validate(data)
    env = errors.from_validation_error(info.value, request_id="req_12345678")
    wire = to_wire(env)
    assert wire["code"] == "validation_failed"
    locs = [d["loc"] for d in wire["details"]]
    assert ["reporter_name"] in locs
    assert any(loc[:2] == ["needs", 1] for loc in locs)
    assert "María" not in str(wire) and "gallons" not in str(wire)
    errors.ErrorEnvelope.model_validate(wire)


def test_profile_violation_helper():
    env = errors.profile_violation(["location", "address_text"], "req_12345678")
    assert env.code == "profile_violation" and env.details[0].loc == ["location", "address_text"]


# ---- FastAPI compatibility -------------------------------------------------


def test_strict_models_work_as_fastapi_bodies_and_responses():
    app = FastAPI()

    @app.post("/reports", response_model=reports.ReportAccepted, response_model_exclude_unset=True)
    def submit(body: reports.ReportSubmission) -> reports.ReportAccepted:
        return reports.ReportAccepted(
            report_id="00000000-0000-4000-8000-000000000099",
            state="confirmed",
            need_ids=[],
            profile_version=1,
            received_at=datetime(2026, 11, 7, 10, tzinfo=timezone.utc),
        )

    client = TestClient(app)
    ok = client.post("/reports", json=SUBMISSION)
    assert ok.status_code == 200, ok.text
    assert ok.json()["received_at"] == "2026-11-07T10:00:00Z"
    bad = client.post("/reports", json={**SUBMISSION, "reporter_name": "x"})
    assert bad.status_code == 422
    schema = app.openapi()
    assert "ReportSubmission" in schema["components"]["schemas"]
