"""Org-scoped read queries against the shared database.

Every function takes an explicit org_id and filters on it — tenant scoping is in
the query, never from a request body. Reports are the center of the model;
power/water status come from the report's observations, needs drive tags.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dash.shared_db import models

Report = models.Report
Need = models.Need
Observation = models.Observation
Area = models.Area
Organization = models.Organization
User = models.User
OrganizationMembership = models.OrganizationMembership
PrivacyProfileVersion = models.PrivacyProfileVersion


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- Auth ------------------------------------------------------------------

def find_user_by_email(db: Session, email: str):
    return db.scalar(select(User).where(User.auth_subject == email))


def user_by_id(db: Session, user_id: str):
    return db.get(User, user_id)


def memberships_for_user(db: Session, user_id: str) -> list[tuple]:
    """Return [(membership, organization), ...] for a user."""
    rows = db.execute(
        select(OrganizationMembership, Organization)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(OrganizationMembership.user_id == user_id,
               OrganizationMembership.status == "active")
    ).all()
    return [(m, o) for (m, o) in rows]


def primary_membership(db: Session, user_id: str):
    rows = memberships_for_user(db, user_id)
    return rows[0] if rows else None


# ---- Area name lookup ------------------------------------------------------

def area_names(db: Session, org_id: str) -> dict[str, str]:
    rows = db.execute(
        select(Area.id, Area.name).where(Area.organization_id == org_id)
    ).all()
    return {aid: name for (aid, name) in rows}


# ---- Reports ---------------------------------------------------------------

def _report_tags(db: Session, org_id: str, report_id: str) -> list[str]:
    tags: list[str] = []
    obs = db.execute(
        select(Observation.service_type, Observation.status)
        .where(Observation.organization_id == org_id,
               Observation.report_id == report_id)
    ).all()
    for svc, status in obs:
        if svc == "electricity" and status in ("unavailable", "intermittent"):
            tags.append("no_power" if status == "unavailable" else "intermittent_power")
        if svc == "piped_water" and status in ("unavailable", "intermittent"):
            tags.append("no_water")
    needs = db.scalars(
        select(Need.category).where(Need.organization_id == org_id,
                                    Need.report_id == report_id)
    ).all()
    for cat in needs:
        tags.append(f"need_{cat}")
    return tags


def _primary_observation(db: Session, org_id: str, report_id: str):
    return db.execute(
        select(Observation.service_type, Observation.status)
        .where(Observation.organization_id == org_id,
               Observation.report_id == report_id)
        .order_by(Observation.observed_at.desc())
    ).first()


def list_reports(db: Session, org_id: str, status: str | None = None, limit: int = 200):
    q = select(Report).where(Report.organization_id == org_id)
    if status:
        q = q.where(Report.status == status)
    q = q.order_by(Report.submitted_at.desc()).limit(limit)
    reports = db.scalars(q).all()
    areas = area_names(db, org_id)
    out = []
    for r in reports:
        prim = _primary_observation(db, org_id, r.id)
        out.append({
            "id": r.id,
            "area": areas.get(r.area_id),
            "status": r.status,
            "urgent": bool(r.urgent_flagged),
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "source_channel": r.source_channel,
            "service_type": prim[0] if prim else None,
            "service_status": prim[1] if prim else None,
            "tags": _report_tags(db, org_id, r.id),
            "reporter_name": None,  # names are encrypted at rest; not decoded in pilot
            "reporter_phone": None,
            "assignee": r.entered_by_membership_id,
        })
    return out


def get_report(db: Session, org_id: str, report_id: str):
    r = db.scalar(
        select(Report).where(Report.organization_id == org_id, Report.id == report_id)
    )
    if r is None:
        return None
    areas = area_names(db, org_id)
    prim = _primary_observation(db, org_id, r.id)
    answers = r.answers_json or {}
    # Build a lightweight transcript from stored answers (no raw message text).
    transcript = [{"from": "reporter", "at": r.submitted_at.isoformat() if r.submitted_at else "",
                   "text": str(answers)}] if answers else []
    obs = db.execute(
        select(Observation.service_type, Observation.status)
        .where(Observation.organization_id == org_id, Observation.report_id == r.id)
    ).all()
    power = next((s for (svc, s) in obs if svc == "electricity"), "unknown")
    water = next((s for (svc, s) in obs if svc == "piped_water"), "unknown")
    return {
        "id": r.id,
        "area": areas.get(r.area_id),
        "status": r.status,
        "urgent": bool(r.urgent_flagged),
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "source_channel": r.source_channel,
        "service_type": prim[0] if prim else None,
        "service_status": prim[1] if prim else None,
        "tags": _report_tags(db, org_id, r.id),
        "reporter_name": None,
        "reporter_phone": None,
        "assignee": r.entered_by_membership_id,
        "notes": (answers.get("_notes") if isinstance(answers, dict) else "") or "",
        "transcript": transcript,
        "extracted_fields": {
            "power_status": power,
            "water_status": water,
            "household_size": answers.get("household_size") if isinstance(answers, dict) else None,
            "urgent_needs": _report_tags(db, org_id, r.id),
        },
    }


def patch_report(db: Session, org_id: str, report_id: str, *, status=None, notes=None, assignee=None):
    r = db.scalar(
        select(Report).where(Report.organization_id == org_id, Report.id == report_id)
    )
    if r is None:
        return None
    if status is not None:
        r.status = status
    if assignee is not None:
        r.entered_by_membership_id = assignee
    if notes is not None:
        answers = dict(r.answers_json or {})
        answers["_notes"] = notes
        r.answers_json = answers
    db.commit()
    return get_report(db, org_id, report_id)


# ---- Dashboard aggregates --------------------------------------------------

def dashboard_metrics(db: Session, org_id: str) -> dict:
    today = _utcnow() - timedelta(hours=24)
    reports_today = db.scalar(
        select(func.count()).select_from(Report)
        .where(Report.organization_id == org_id, Report.submitted_at >= today)
    ) or 0
    # Distinct reports with an unavailable/intermittent observation per service.
    def _count_service(svc: str) -> int:
        return db.scalar(
            select(func.count(func.distinct(Observation.report_id)))
            .where(Observation.organization_id == org_id,
                   Observation.service_type == svc,
                   Observation.status.in_(("unavailable", "intermittent")))
        ) or 0
    urgent = db.scalar(
        select(func.count()).select_from(Report)
        .where(Report.organization_id == org_id, Report.urgent_flagged.is_(True))
    ) or 0
    return {
        "reports_today": int(reports_today),
        "without_power": _count_service("electricity"),
        "without_water": _count_service("piped_water"),
        "urgent": int(urgent),
    }


def area_breakdown(db: Session, org_id: str) -> list[dict]:
    areas = area_names(db, org_id)
    out = []
    for area_id, name in areas.items():
        reports = db.scalar(
            select(func.count()).select_from(Report)
            .where(Report.organization_id == org_id, Report.area_id == area_id)
        ) or 0
        if reports == 0:
            continue
        def _svc(svc):
            return db.scalar(
                select(func.count(func.distinct(Observation.report_id)))
                .where(Observation.organization_id == org_id,
                       Observation.area_id == area_id,
                       Observation.service_type == svc,
                       Observation.status.in_(("unavailable", "intermittent")))
            ) or 0
        urgent = db.scalar(
            select(func.count()).select_from(Report)
            .where(Report.organization_id == org_id, Report.area_id == area_id,
                   Report.urgent_flagged.is_(True))
        ) or 0
        out.append({"area": name, "reports": int(reports),
                    "without_power": int(_svc("electricity")),
                    "without_water": int(_svc("piped_water")),
                    "urgent": int(urgent)})
    out.sort(key=lambda a: a["reports"], reverse=True)
    return out


def campaign_answers(db: Session, org_id: str, campaign_id: str | None = None,
                     limit: int = 5000) -> list[dict]:
    """Return the ``answers_json`` of each report for the org (optionally scoped to
    one campaign). Custom campaign-field answers live under their field id here."""
    q = select(Report.answers_json).where(Report.organization_id == org_id)
    if campaign_id is not None:
        q = q.where(Report.campaign_id == campaign_id)
    q = q.limit(limit)
    rows = db.scalars(q).all()
    return [dict(a) for a in rows if isinstance(a, dict)]


def feed(db: Session, org_id: str, since: str | None = None, limit: int = 20) -> list[dict]:
    q = select(Report).where(Report.organization_id == org_id)
    if since:
        try:
            q = q.where(Report.submitted_at < datetime.fromisoformat(since))
        except ValueError:
            pass
    q = q.order_by(Report.submitted_at.desc()).limit(limit)
    reports = db.scalars(q).all()
    areas = area_names(db, org_id)
    out = []
    for r in reports:
        answers = r.answers_json or {}
        preview = ""
        if isinstance(answers, dict):
            preview = str(answers.get("summary") or answers.get("note") or "")
        out.append({
            "id": r.id,
            "received_at": r.submitted_at.isoformat() if r.submitted_at else "",
            "area": areas.get(r.area_id),
            "channel": r.source_channel,
            "preview": preview or "(report submitted)",
            "tags": _report_tags(db, org_id, r.id),
            "report_id": r.id,
        })
    return out
