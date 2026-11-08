"""Reports: submission, draft/confirm, corrections, reporter keys, repeat linking
(DOM-010..017).

Pure functions return new frozen values; the command layer persists them, the
audit event, and any outbound intent in one transaction (DOM-003).
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.domain.errors import InvalidTransition, ValidationFailed
from app.domain.ports import IdGenerator
from app.domain.profiles import validate_submission
from app.domain.types import (
    EXCLUDING_DISPOSITIONS,
    AddressLocation,
    DomainContext,
    Need,
    NeedState,
    Observation,
    PermissionPurpose,
    PrivacyProfile,
    Relationship,
    Report,
    ReportState,
    ReportSubmission,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# DOM-004: report transition table.
REPORT_TRANSITIONS: frozenset[tuple[ReportState, ReportState]] = frozenset(
    {
        (ReportState.draft, ReportState.confirmed),
        (ReportState.draft, ReportState.abandoned),
        (ReportState.confirmed, ReportState.superseded),
    }
)


def _transition(report: Report, to: ReportState) -> None:
    if (report.state, to) not in REPORT_TRANSITIONS:
        raise InvalidTransition("report", report.state.value, to.value)


# ---------------------------------------------------------------------------
# Reporter key (DOM-014)
# ---------------------------------------------------------------------------


def normalize_endpoint(endpoint: str) -> str:
    digits = "".join(ch for ch in endpoint if ch.isdigit())
    if not digits:
        raise ValidationFailed("contact endpoint has no digits")
    return digits


def rotation_epoch(now: datetime, rotation_days: int) -> int:
    return int((now - _EPOCH).total_seconds() // (rotation_days * 86400))


def reporter_key(org_secret: bytes, org_id: str, endpoint: str, now: datetime, rotation_days: int) -> str:
    """Org-scoped HMAC of the contact endpoint, rotated per the profile.

    The same phone in the same org and rotation period yields the same key; a
    different org or period yields an unrelated key.
    """
    msg = f"{org_id}|{rotation_epoch(now, rotation_days)}|{normalize_endpoint(endpoint)}".encode()
    return "rk_" + hmac.new(org_secret, msg, hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Submit, confirm, abandon (DOM-010/011)
# ---------------------------------------------------------------------------


def submit_report(
    ctx: DomainContext,
    sub: ReportSubmission,
    profile: PrivacyProfile,
    now: datetime,
    ids: IdGenerator,
    reporter_key: Optional[str] = None,
) -> Report:
    """Create a draft report under ``profile`` (the capture profile, see
    profiles.capture_profile). Raises ProfileViolation for disallowed fields."""
    if profile.org_id != ctx.org_id:
        raise ValidationFailed("profile belongs to another org")
    validate_submission(sub, profile)
    report_id = ids.new_id("rep")
    area_only = sub.relationship is Relationship.area
    observations = tuple(
        Observation(
            id=ids.new_id("obs"),
            report_id=report_id,
            service=o.service,
            status=o.status,
            observed_at=o.observed_at,
            observed_precision=o.observed_precision,
            outage_onset=o.outage_onset,
            onset_precision=o.onset_precision,
        )
        for o in sub.observations
    )
    needs = tuple(
        Need(
            id=ids.new_id("need"),
            report_id=report_id,
            category=n.category,
            state=NeedState.active,
            stated_urgency=n.stated_urgency,
            remaining_supply=n.remaining_supply,
            created_at=now,
            last_confirmed_at=now,
            people_affected=n.people_affected,
            quantity=n.quantity,
            access_notes=n.access_notes,
            preferred_times=n.preferred_times,
            state_changed_at=now,
        )
        for n in sub.needs
    )
    permissions = sub.permissions
    if area_only:
        # SEC-02: area-only reports keep no follow-up permissions.
        permissions = frozenset(p for p in permissions if p is PermissionPurpose.notice_ack)
    return Report(
        id=report_id,
        org_id=ctx.org_id,
        channel=sub.channel,
        relationship=sub.relationship,
        area_id=sub.area_id,
        state=ReportState.draft,
        profile_version=profile.version,
        notice_version=sub.notice_version,
        questionnaire_version=sub.questionnaire_version,
        submitted_at=now,
        reporter_key=reporter_key,
        location=None if area_only and isinstance(sub.location, AddressLocation) else sub.location,
        observations=observations,
        needs=needs,
        permissions=permissions,
        reporter_name_encrypted=None if area_only else sub.reporter_name_encrypted,
        household_ref=None if area_only else sub.household_ref,
        source_digest=sub.source_digest,
    )


def confirm_report(report: Report, now: datetime) -> Report:
    _transition(report, ReportState.confirmed)
    return replace(report, state=ReportState.confirmed, confirmed_at=now)


def abandon_draft(report: Report) -> Report:
    """Abandoned drafts contribute nothing; needs are dropped with them."""
    _transition(report, ReportState.abandoned)
    return replace(report, state=ReportState.abandoned)


def is_aggregatable(report: Report) -> bool:
    """The single inclusion rule used by indicators (DOM-011/012/072/073).

    Confirmed, not superseded, and not excluded by a human duplicate/spam
    disposition. Nothing else — not disagreement, frequency, external data, or a
    shared phone — removes a report.
    """
    return (
        report.state is ReportState.confirmed
        and report.superseded_by_id is None
        and report.disposition not in EXCLUDING_DISPOSITIONS
    )


# ---------------------------------------------------------------------------
# Corrections (DOM-012)
# ---------------------------------------------------------------------------


def correct_report(
    ctx: DomainContext,
    prior: Report,
    sub: ReportSubmission,
    profile: PrivacyProfile,
    now: datetime,
    ids: IdGenerator,
) -> tuple[Report, Report]:
    """Supersede ``prior`` with a confirmed correction. Returns (prior', correction).

    ``profile`` must be the most restrictive of the prior's collection profile and
    the active one (profiles.validate_report_update) so a correction never enriches.
    Needs of the same category keep their identity history via ``linked_need_id``
    and their original ``created_at`` (age of the oldest unmet need).
    """
    if prior.org_id != ctx.org_id:
        raise ValidationFailed("report belongs to another org")
    _transition(prior, ReportState.superseded)
    draft = submit_report(ctx, sub, profile, now, ids, reporter_key=prior.reporter_key)
    prior_needs = {n.category: n for n in prior.needs}
    linked = []
    for n in draft.needs:
        p = prior_needs.get(n.category)
        if p is not None:
            n = replace(
                n,
                linked_need_id=p.id,
                created_at=p.created_at,
                refresh_prompts_sent=p.refresh_prompts_sent,
                last_prompted_at=p.last_prompted_at,
            )
        linked.append(n)
    correction = replace(
        confirm_report(draft, now),
        needs=tuple(linked),
        supersedes_id=prior.id,
        disposition=prior.disposition,
        duplicate_of_id=prior.duplicate_of_id,
        exclusion_reason=prior.exclusion_reason,
    )
    superseded = replace(prior, state=ReportState.superseded, superseded_by_id=correction.id)
    return superseded, correction


# ---------------------------------------------------------------------------
# Repeat reporters (DOM-014)
# ---------------------------------------------------------------------------


def link_repeat(new_report: Report, prior_reports: Iterable[Report], now: datetime) -> tuple[Report, list[Need]]:
    """Link a newly confirmed report to the same reporter key's open needs.

    For each category in the new report, the reporter's open need of that
    category is marked ``replaced_by_id`` (it is the same need, restated) and the
    new need inherits its ``created_at``. Returns (new_report', replaced prior needs).
    A change of status over time is a transition, never a conflict.
    """
    if new_report.reporter_key is None:
        return new_report, []
    open_by_cat: dict = {}
    for r in prior_reports:
        if r.id == new_report.id or r.reporter_key != new_report.reporter_key or r.org_id != new_report.org_id:
            continue
        if not is_aggregatable(r):
            continue
        for n in r.needs:
            if n.is_open:
                cur = open_by_cat.get(n.category)
                if cur is None or n.created_at < cur.created_at:
                    open_by_cat[n.category] = n
    replaced: list[Need] = []
    new_needs = []
    for n in new_report.needs:
        prior = open_by_cat.get(n.category)
        if prior is not None:
            replaced.append(replace(prior, replaced_by_id=n.id))
            n = replace(
                n,
                linked_need_id=prior.id,
                created_at=prior.created_at,
                refresh_prompts_sent=prior.refresh_prompts_sent,
                last_prompted_at=prior.last_prompted_at,
            )
        new_needs.append(n)
    return replace(new_report, needs=tuple(new_needs)), replaced


def report_watermark(report: Report) -> str:
    """Sortable watermark: confirmed time + id."""
    at = report.confirmed_at or report.submitted_at
    return f"{at.isoformat()}|{report.id}"
