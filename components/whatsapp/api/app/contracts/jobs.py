"""Internal operational-worker job payloads (CON-021).

Each job carries only IDs, the organization, an operation key and the schema
version. Workers load everything else from the database under that organization's
scope, so a queued payload never holds personal data. ``InternalJob`` is the
discriminated union a worker validates against. Exported to ``schemas/events/v1/``.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from .base import ContractModel, OperationKey, Uuid

JOB_SCHEMA_VERSION = "1"


class _JobBase(ContractModel):
    schema_version: Literal["1"]
    job_id: Uuid
    organization_id: Uuid
    operation_key: OperationKey


class IntakeProcessJob(_JobBase):
    job_type: Literal["intake_process"]
    inbound_event_id: Uuid


class MessageSendJob(_JobBase):
    job_type: Literal["message_send"]
    outbound_intent_id: Uuid


class MessageStatusJob(_JobBase):
    job_type: Literal["message_status"]
    status_event_id: Uuid


class EvidenceIngestJob(_JobBase):
    job_type: Literal["evidence_ingest"]
    data_job_result_id: Uuid


class IndicatorRefreshJob(_JobBase):
    job_type: Literal["indicator_refresh"]
    area_ids: Annotated[list[Uuid], Field(min_length=1, max_length=500)]


class AlertEvaluateJob(_JobBase):
    job_type: Literal["alert_evaluate"]
    indicator_snapshot_id: Uuid


class RefreshPromptJob(_JobBase):
    job_type: Literal["refresh_prompt"]
    need_id: Uuid


class BroadcastJob(_JobBase):
    job_type: Literal["broadcast"]
    broadcast_id: Uuid


class RetentionJob(_JobBase):
    job_type: Literal["retention"]
    policy_version_id: Uuid


InternalJob = Annotated[
    Union[
        IntakeProcessJob,
        MessageSendJob,
        MessageStatusJob,
        EvidenceIngestJob,
        IndicatorRefreshJob,
        AlertEvaluateJob,
        RefreshPromptJob,
        BroadcastJob,
        RetentionJob,
    ],
    Field(discriminator="job_type"),
]

JOB_MODELS = (
    IntakeProcessJob,
    MessageSendJob,
    MessageStatusJob,
    EvidenceIngestJob,
    IndicatorRefreshJob,
    AlertEvaluateJob,
    RefreshPromptJob,
    BroadcastJob,
    RetentionJob,
)
