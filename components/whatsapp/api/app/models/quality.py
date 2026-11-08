"""Data quality: links, review, duplicates, merges, data jobs (DB-014, DB-024).

Review tasks use typed nullable target columns (each an org-scoped FK) and a
CHECK that at least one is set, instead of unchecked generic IDs.
``review_decision`` and ``merge_event`` are append-only.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    AppendOnly, Base, JSONType, TenantOwned, check_in, org_fk, org_scoped, utcnow,
)

LINK_RELATIONS = ("duplicate_of", "same_source", "conflicts_with", "corroborates")
REVIEW_REASONS = ("duplicate_candidate", "conflicting_observations", "unresolved_location",
                  "flood_or_burst", "outlier_cell", "urgent_flag", "unparsed_text")
REVIEW_STATUSES = ("open", "in_review", "resolved", "dismissed")
DISPOSITIONS = ("valid", "duplicate", "spam", "location_corrected", "unresolved")
ENTITY_TYPES = ("report", "observation", "need")
CANDIDATE_STATUSES = ("open", "confirmed", "rejected")
DATA_JOB_STATUSES = ("queued", "leased", "succeeded", "failed", "cancelled")


class ObservationLink(TenantOwned, Base):
    __tablename__ = "observation_link"
    __table_args__ = org_scoped(
        "observation_link",
        org_fk("observation_link", "observation_a_id", "observation", ondelete="CASCADE"),
        org_fk("observation_link", "observation_b_id", "observation", ondelete="CASCADE"),
        org_fk("observation_link", "created_by_membership_id", "organization_membership"),
        check_in("observation_link", "relation", LINK_RELATIONS),
        # One unordered pair per relation, no self-links (DB-024).
        CheckConstraint("observation_a_id < observation_b_id", name="ck_observation_link_order"),
        UniqueConstraint("organization_id", "observation_a_id", "observation_b_id", "relation",
                         name="uq_observation_link"),
    )

    observation_a_id: Mapped[str] = mapped_column(String(36), nullable=False)
    observation_b_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons_json: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DuplicateCandidate(TenantOwned, Base):
    __tablename__ = "duplicate_candidate"
    __table_args__ = org_scoped(
        "duplicate_candidate",
        org_fk("duplicate_candidate", "reviewed_by_membership_id", "organization_membership"),
        check_in("duplicate_candidate", "entity_type", ENTITY_TYPES),
        check_in("duplicate_candidate", "status", CANDIDATE_STATUSES),
        CheckConstraint("entity_a_id < entity_b_id", name="ck_duplicate_candidate_order"),
        UniqueConstraint("organization_id", "entity_type", "entity_a_id", "entity_b_id",
                         name="uq_duplicate_candidate"),
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_a_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entity_b_id: Mapped[str] = mapped_column(String(36), nullable=False)
    match_reasons: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    reviewed_by_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ReviewTask(TenantOwned, Base):
    __tablename__ = "review_task"
    __table_args__ = org_scoped(
        "review_task",
        org_fk("review_task", "report_id", "report"),
        org_fk("review_task", "observation_id", "observation"),
        org_fk("review_task", "need_id", "need"),
        org_fk("review_task", "area_id", "area"),
        org_fk("review_task", "duplicate_candidate_id", "duplicate_candidate"),
        org_fk("review_task", "assigned_membership_id", "organization_membership"),
        check_in("review_task", "reason", REVIEW_REASONS),
        check_in("review_task", "status", REVIEW_STATUSES),
        CheckConstraint(
            "report_id IS NOT NULL OR observation_id IS NOT NULL OR need_id IS NOT NULL "
            "OR area_id IS NOT NULL OR duplicate_candidate_id IS NOT NULL",
            name="ck_review_task_target"),
        Index("ix_review_task_queue", "organization_id", "status", "assigned_membership_id"),
    )

    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    report_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    observation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    need_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    area_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    duplicate_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reasons_json: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    assigned_membership_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewDecision(AppendOnly, TenantOwned, Base):
    __tablename__ = "review_decision"
    __table_args__ = org_scoped(
        "review_decision",
        org_fk("review_decision", "review_task_id", "review_task"),
        org_fk("review_decision", "reviewer_membership_id", "organization_membership"),
        check_in("review_decision", "disposition", DISPOSITIONS),
    )

    review_task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_membership_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 default=utcnow)
    review_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MergeEvent(AppendOnly, TenantOwned, Base):
    __tablename__ = "merge_event"
    __table_args__ = org_scoped(
        "merge_event",
        org_fk("merge_event", "approved_by_membership_id", "organization_membership"),
        org_fk("merge_event", "reverses_merge_event_id", "merge_event"),
        check_in("merge_event", "entity_type", ENTITY_TYPES),
        CheckConstraint("source_id <> destination_id", name="ck_merge_event_distinct"),
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    destination_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_membership_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  default=utcnow)
    # A reversal is a new merge_event pointing at the one it reverses.
    reverses_merge_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DataJob(TenantOwned, Base):
    """Application-owned data-worker job with a fenced lease (DB-014).

    ``lease_fence`` increments on every claim; a result is accepted only with
    the current fence, so a worker whose lease expired cannot commit.
    """

    __tablename__ = "data_job"
    __table_args__ = org_scoped(
        "data_job",
        check_in("data_job", "status", DATA_JOB_STATUSES),
        CheckConstraint("attempts >= 0 AND lease_fence >= 0", name="ck_data_job_counters"),
        Index("ix_data_job_claim", "status", "run_after"),
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_fence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataJobResult(TenantOwned, Base):
    __tablename__ = "data_job_result"
    __table_args__ = org_scoped(
        "data_job_result",
        org_fk("data_job_result", "data_job_id", "data_job", ondelete="CASCADE"),
        UniqueConstraint("data_job_id", "lease_fence", name="uq_data_job_result_fence"),
    )

    data_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_fence: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # DB-080 restricted object reference.
    object_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
