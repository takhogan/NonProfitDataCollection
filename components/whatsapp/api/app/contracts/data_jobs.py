"""Data-job protocol between the backend and the separate data worker (CON-022, CON-023).

See ``components/contracts/data-jobs.md``. The data worker never imports this
package: it validates against the JSON Schemas exported to
``components/contracts/schemas/data-jobs/v1/``. Rules that JSON Schema can state
(required-if, unit per indicator type) are written into the schema too, so both
validators agree on the shared fixtures. Rules it cannot state (window ordering,
bounded window length) are Pydantic-only and the API enforces them.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .base import (
    ContractModel,
    OperationKey,
    ServiceType,
    Slug,
    TimePrecision,
    UtcInstant,
    Uuid,
    not_asked,
)
from .reports import ObservationStatus

DATA_JOB_SCHEMA_VERSION = "1"
MAX_OBSERVATION_WINDOW = timedelta(days=92)

IndicatorType = Literal["monitor_ciudad_service_status", "ntl_radiance_anomaly", "rainfall_anomaly"]
"""P0, P1 and P2 respectively."""

INDICATOR_UNIT: dict[str, str] = {
    "monitor_ciudad_service_status": "share",  # share of informants reporting an outage, 0..1
    "ntl_radiance_anomaly": "z_score",
    "rainfall_anomaly": "mm",
}

AttemptToken = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_-]{32,128}$")]
"""Lease credential for one attempt. Never logged, never written into artifacts."""
VersionString = Annotated[str, StringConstraints(pattern="^[A-Za-z0-9._-]{1,64}$")]
ReferenceString = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ParamKey = Annotated[str, StringConstraints(pattern="^[a-z][a-z0-9_]{0,63}$")]
ParamValue = Union[
    Annotated[str, StringConstraints(max_length=256)],
    int,
    float,
    bool,
]


class TimeWindow(ContractModel):
    start: UtcInstant
    end: UtcInstant

    @model_validator(mode="after")
    def _order(self) -> "TimeWindow":
        if self.end <= self.start:
            raise ValueError("window end must be after start")
        return self


class AreaGeometryReference(ContractModel):
    """Resolved through scoped API access; the job never embeds geometry."""

    geometry_id: Uuid
    geometry_version: Annotated[int, Field(ge=1)]
    crs: Literal["EPSG:4326"]


class DataJobRequest(ContractModel):
    """Returned by ``POST /internal/data-jobs/claim``. Scope comes from the persisted job,
    never from these fields alone."""

    schema_version: Literal["1"]
    job_id: Uuid
    organization_id: Uuid
    job_type: IndicatorType
    operation_key: OperationKey
    source_id: Slug = Field(description="An approved source ID, never a URL.")
    source_version: VersionString = not_asked()
    area_id: Uuid
    area_geometry_reference: AreaGeometryReference
    service_type: ServiceType
    observation_window_start: UtcInstant
    observation_window_end: UtcInstant
    baseline_window: TimeWindow = not_asked()
    parameters: Annotated[
        dict[ParamKey, ParamValue],
        Field(max_length=20, json_schema_extra={"additionalProperties": False}),
    ]
    processing_version: VersionString
    attempt_token: AttemptToken
    lease_expires_at: UtcInstant

    @model_validator(mode="after")
    def _window(self) -> "DataJobRequest":
        span = self.observation_window_end - self.observation_window_start
        if span <= timedelta(0):
            raise ValueError("observation window end must be after start")
        if span > MAX_OBSERVATION_WINDOW:
            raise ValueError("observation window is longer than 92 days")
        return self


class SpatialResolution(ContractModel):
    value: Annotated[float, Field(gt=0, le=1_000_000)]
    unit: Literal["m"]


class ArtifactReference(ContractModel):
    """An object in restricted storage uploaded under this job's authorization.

    The checksum sits with its reference (``data-jobs.md`` lists ``artifact_checksums[]``
    as a parallel array; one object per artifact avoids misaligned arrays)."""

    object_key: Annotated[str, StringConstraints(pattern="^[A-Za-z0-9/_.-]{1,512}$")]
    media_type: Annotated[str, StringConstraints(pattern="^[a-z]+/[A-Za-z0-9.+-]+$", max_length=128)]
    size_bytes: Annotated[int, Field(ge=0, le=5_000_000_000)]
    sha256: Annotated[str, StringConstraints(pattern="^[0-9a-f]{64}$")]


def _result_schema_rules() -> dict:
    unit_rules = [
        {
            "if": {"properties": {"indicator_type": {"const": t}}, "required": ["unit"]},
            "then": {"properties": {"unit": {"const": u}}},
        }
        for t, u in INDICATOR_UNIT.items()
    ]
    return {
        "allOf": [
            {
                "if": {"properties": {"data_availability": {"const": "unavailable"}}},
                "then": {"not": {"anyOf": [{"required": ["value"]}, {"required": ["unit"]}]}},
            },
            {
                "if": {"properties": {"data_availability": {"const": "usable"}}},
                "then": {"required": ["value", "unit"]},
            },
            {"dependentRequired": {"value": ["unit"], "unit": ["value"]}},
            *unit_rules,
        ]
    }


class DataJobResult(ContractModel):
    """A worker's result. An unavailable result has no value: absence never becomes zero."""

    model_config = ConfigDict(json_schema_extra=_result_schema_rules())

    schema_version: Literal["1"]
    job_id: Uuid
    operation_key: OperationKey
    processing_version: VersionString
    source_id: Slug
    source_version: VersionString = not_asked()
    source_reference: ReferenceString
    license_reference: ReferenceString
    observed_from: UtcInstant
    observed_to: UtcInstant
    retrieved_at: UtcInstant
    area_id: Uuid
    geometry_version: Annotated[int, Field(ge=1)]
    spatial_resolution: SpatialResolution = not_asked()
    temporal_resolution: Literal["PT1H", "PT6H", "P1D", "P7D", "P1M"] = not_asked()
    indicator_type: IndicatorType
    value: Annotated[float, Field(ge=-1_000_000, le=1_000_000)] = not_asked()
    unit: Literal["share", "z_score", "mm"] = not_asked()
    baseline_reference: ReferenceString = not_asked()
    method_version: VersionString
    quality_flags: Annotated[list[Annotated[str, StringConstraints(pattern="^[a-z0-9_]{1,64}$")]], Field(max_length=20)]
    limitations: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=500)]], Field(max_length=20)]
    data_availability: Literal["usable", "partial", "unavailable"]
    artifact_references: Annotated[list[ArtifactReference], Field(max_length=50)]

    @model_validator(mode="after")
    def _check(self) -> "DataJobResult":
        if self.observed_to < self.observed_from:
            raise ValueError("observed_to must not be before observed_from")
        if self.data_availability == "unavailable" and (self.value is not None or self.unit is not None):
            raise ValueError("an unavailable result has no value or unit")
        if self.data_availability == "usable" and (self.value is None or self.unit is None):
            raise ValueError("a usable result has a value and unit")
        if (self.value is None) != (self.unit is None):
            raise ValueError("value and unit go together")
        if self.unit is not None and self.unit != INDICATOR_UNIT[self.indicator_type]:
            raise ValueError(f"unit for {self.indicator_type} must be '{INDICATOR_UNIT[self.indicator_type]}'")
        if self.indicator_type == "monitor_ciudad_service_status" and self.value is not None:
            if not 0 <= self.value <= 1:
                raise ValueError("a share is between 0 and 1")
        return self


class DataJobComplete(ContractModel):
    """Body of ``POST /internal/data-jobs/{id}/complete``."""

    schema_version: Literal["1"]
    attempt_token: AttemptToken
    result: DataJobResult


class DataJobHeartbeat(ContractModel):
    """Body of ``POST /internal/data-jobs/{id}/heartbeat``."""

    schema_version: Literal["1"]
    attempt_token: AttemptToken


class DataJobLease(ContractModel):
    """Response to a heartbeat: the renewed lease."""

    schema_version: Literal["1"]
    job_id: Uuid
    lease_expires_at: UtcInstant


class DataJobFailure(ContractModel):
    """Body of ``POST /internal/data-jobs/{id}/fail``. ``message`` must already be redacted."""

    schema_version: Literal["1"]
    attempt_token: AttemptToken
    classification: Literal["retryable", "terminal"]
    reason_code: Annotated[str, StringConstraints(pattern="^[a-z0-9_]{1,64}$")]
    message: Annotated[str, StringConstraints(max_length=1000)] = not_asked()


# ---- Mock Monitor Ciudad upstream record (CON-023) -------------------------


class MonitorCiudadReport(ContractModel):
    """Assumed upstream record used by the mock source until D10 is resolved."""

    model_config = ConfigDict(
        title="MonitorCiudadReport",
        json_schema_extra={
            "x-assumed": True,
            "oneOf": [{"required": ["area_code"]}, {"required": ["area_alias"]}],
        },
    )

    schema_version: Literal["1"]
    informant_id: Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_-]{8,64}$")] = Field(
        description="Pseudonymous informant ID; never a phone number or name."
    )
    area_code: Annotated[str, StringConstraints(pattern="^[A-Z0-9-]{2,32}$")] = not_asked()
    area_alias: Annotated[str, StringConstraints(min_length=1, max_length=128)] = not_asked()
    service: ServiceType
    status: ObservationStatus
    observed_at: UtcInstant
    observed_at_precision: TimePrecision
    hours_without_service: Annotated[float, Field(ge=0, le=24 * 60)] = not_asked()
    submitted_at: UtcInstant

    @model_validator(mode="after")
    def _area(self) -> "MonitorCiudadReport":
        if (self.area_code is None) == (self.area_alias is None):
            raise ValueError("exactly one of area_code or area_alias")
        return self
