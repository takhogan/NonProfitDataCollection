"""Exported JSON Schemas: ``components/contracts/schemas/<group>/v1/<name>.json``.

The data worker and other non-Python consumers validate against these files. The
export script writes them; a test fails when they are stale.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter

from . import admin, aggregation, data_jobs, errors, events, jobs, providers, public, questionnaires, reports

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# (group, name) -> type. Each group is exported under "<group>/v1/".
EXPORTED: dict[tuple[str, str], Any] = {
    ("events", "inbound_message"): events.InboundMessage,
    ("events", "delivery_status_event"): events.DeliveryStatusEvent,
    ("events", "internal_job"): jobs.InternalJob,
    **{("events", m.model_fields["job_type"].annotation.__args__[0] + "_job"): m for m in jobs.JOB_MODELS},
    ("data-jobs", "data_job_request"): data_jobs.DataJobRequest,
    ("data-jobs", "data_job_result"): data_jobs.DataJobResult,
    ("data-jobs", "data_job_complete"): data_jobs.DataJobComplete,
    ("data-jobs", "data_job_heartbeat"): data_jobs.DataJobHeartbeat,
    ("data-jobs", "data_job_lease"): data_jobs.DataJobLease,
    ("data-jobs", "data_job_failure"): data_jobs.DataJobFailure,
    ("data-jobs", "monitor_ciudad_report"): data_jobs.MonitorCiudadReport,
    ("questionnaires", "questionnaire_definition"): questionnaires.QuestionnaireDefinition,
}

SCHEMA_VERSION = "v1"

_TITLES = {jobs.InternalJob: "InternalJob"}


def _strip_null_defaults(node: Any) -> Any:
    """Remove ``default: null`` that would contradict a non-null type (CON-003)."""
    if isinstance(node, dict):
        if node.get("default", object()) is None:
            node = {k: v for k, v in node.items() if k != "default"}
        return {k: _strip_null_defaults(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_null_defaults(v) for v in node]
    return node


def build_schema(tp: Any) -> dict[str, Any]:
    schema = TypeAdapter(tp).json_schema(mode="validation")
    schema = _strip_null_defaults(schema)
    if tp in _TITLES:
        schema["title"] = _TITLES[tp]
    out = {"$schema": JSON_SCHEMA_DIALECT, "x-contract-version": SCHEMA_VERSION}
    out.update(schema)
    return out


def render(tp: Any) -> str:
    return json.dumps(build_schema(tp), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def relative_path(group: str, name: str) -> str:
    return f"schemas/{group}/{SCHEMA_VERSION}/{name}.json"


# API payload models with shared fixtures. Their schemas ship in openapi.json
# (CON-043), not as separate files; tests build their JSON Schema on the fly.
API_FIXTURE_MODELS: dict[str, Any] = {
    "report_submission": reports.ReportSubmission,
    "report_draft": reports.ReportDraft,
    "indicator_cell": aggregation.IndicatorCell,
    "area_of_need": aggregation.AreaOfNeed,
    "coverage_cell": aggregation.CoverageCell,
    "activity": providers.Activity,
    "activity_input": providers.ActivityInput,
    "alert_subscription": providers.AlertSubscription,
    "alert": providers.Alert,
    "api_key_created": providers.ApiKeyCreated,
    "contact_list_row": providers.ContactListRow,
    "public_indicator_cell": public.PublicIndicatorCell,
    "public_activity": public.PublicActivity,
    "privacy_profile": admin.PrivacyProfile,
    "meeting_point": admin.MeetingPoint,
    "broadcast": admin.Broadcast,
    "review_task": admin.ReviewTask,
    "review_disposition_input": admin.ReviewDispositionInput,
    "error_envelope": errors.ErrorEnvelope,
}

# Every fixture directory name -> type.
FIXTURE_MODELS: dict[str, Any] = {name: tp for (_, name), tp in EXPORTED.items()} | API_FIXTURE_MODELS
EXPORTED_BY_NAME: dict[str, tuple[str, str]] = {name: (group, name) for (group, name) in EXPORTED}
