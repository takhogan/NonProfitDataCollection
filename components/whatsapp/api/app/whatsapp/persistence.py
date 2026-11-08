"""Write a confirmed WhatsApp report into the pilot tables (OPW-014..016, OPW-019).

Called by the engine when the resident confirms the summary, inside the same
tenant transaction that queues the confirmation reply. Writes:

- ``report`` (status ``confirmed``) with the engine answers in ``answers_json``
  (address, GPS and notes stay encrypted inside it)
- ``report_location`` (address profile only): encrypted address / restricted point
- ``observation`` rows for electricity and piped water
- ``need`` rows plus ``water_need_detail`` / ``charging_need_detail`` /
  ``charging_device_request``
- ``permission`` rows for the three purposes (granted or denied; OPW-015)
- ``review_task`` rows for urgent reports, unreadable text, unresolved location

Corrections and updates supersede the earlier report (DOM-012). In the
protective profile a new report always supersedes the reporter's latest one
(OPW-019).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import decrypt_text, encrypt
from app.models.quality import ReviewTask
from app.models.report import (
    ChargingDeviceRequest, ChargingNeedDetail, Need, Observation, Report, ReportLocation,
    WaterNeedDetail,
)
from app.models.reporting import Permission, ReporterKey

CARACAS = ZoneInfo("America/Caracas")
_PERMS = (("refresh_prompts", "perm_refresh"), ("area_broadcasts", "perm_area"),
          ("contact_list", "perm_contact"))


@dataclass
class PersistResult:
    report_id: str
    superseded: bool
    need_ids: list[str]
    observation_ids: list[str]


def _onset(now: datetime, days_ago) -> tuple[datetime | None, str | None]:
    if days_ago is None:
        return None, None
    local_midnight = datetime.combine((now.astimezone(CARACAS) - timedelta(days=days_ago)).date(),
                                      time(0, 0), CARACAS)
    return local_midnight, "day"


def persist_report(db: Session, ctx, state: dict, key: ReporterKey, *, evidence: str
                   ) -> PersistResult:
    org = ctx.org_id
    now = ctx.now
    a = dict(state["answers"])
    profile = ctx.profile
    area_id = a.get("sector_id") or a.get("parish_id")
    loc = a.get("location") or {}

    # --- supersede (correction / update / protective repeat) ---
    supersedes = state.get("supersedes")
    if supersedes is None and profile.profile_key == "protective":
        supersedes = db.scalar(select(Report.id).where(
            Report.organization_id == org, Report.reporter_key_id == key.id,
            Report.status == "confirmed").order_by(Report.confirmed_at.desc()).limit(1))
    old = db.get(Report, supersedes) if supersedes else None
    if old is not None and (old.organization_id != org or old.status != "confirmed"):
        old = None

    if area_id is None:
        location_kind = "unresolved"
    elif profile.location_mode == "meeting_point":
        location_kind = {"meeting_point": "meeting_point",
                         "none_nearby": "none_nearby"}.get(loc.get("kind"), "area_only")
    else:
        location_kind = "address" if loc.get("kind") == "address" else "area_only"

    stored = {k: v for k, v in a.items() if not k.startswith("_")}
    report = Report(
        organization_id=org,
        privacy_profile_version_id=profile.id,
        reporter_key_id=key.id,
        campaign_id=ctx.campaign.id if ctx.campaign else None,
        conversation_id=ctx.conversation.id,
        questionnaire_version_id=ctx.campaign.questionnaire_version_id if ctx.campaign else None,
        source_channel="whatsapp",
        reporting_relationship="household",
        area_id=area_id,
        location_kind=location_kind,
        meeting_point_id=loc.get("meeting_point_id") if location_kind == "meeting_point" else None,
        answers_json={"engine": stored, "notes": state.get("notes", []),
                      "flags": state.get("flags", []), "prefilled": state.get("prefilled", []),
                      "evidence": f"whatsapp:{evidence}"},
        status="confirmed",
        submitted_at=now,
        confirmed_at=now,
        urgent_flagged=a.get("urgent") is True,
    )
    if old is not None:
        old.status = "superseded"
        db.flush()  # free the old row before the new one points at it
        report.supersedes_report_id = old.id
    db.add(report)
    db.flush()

    # --- restricted location (address profile only; DB-023 trigger enforces it) ---
    if profile.location_mode == "address" and loc.get("kind") == "address":
        rl = ReportLocation(organization_id=org, report_id=report.id, source="reporter")
        if loc.get("address"):
            rl.encrypted_address = encrypt(decrypt_text(loc["address"]))
        if loc.get("point") and profile.gps_allowed:
            lon, lat = decrypt_text(loc["point"]).split(",")
            rl.restricted_point = f"SRID=4326;POINT({float(lon):.6f} {float(lat):.6f})"
            rl.precision = "exact"
        db.add(rl)

    # --- observations ---
    obs_ids = []
    for service, field_, since in (("electricity", "electricity", "electricity_since"),
                                   ("piped_water", "water", "water_since")):
        status = a.get(field_) or "unknown"
        onset, precision = (_onset(now, a.get(since))
                            if status in ("unavailable", "intermittent") else (None, None))
        o = Observation(organization_id=org, report_id=report.id, area_id=area_id,
                        service_type=service, subject_scope="household", status=status,
                        observed_at=now, time_precision="exact",
                        outage_started_at=onset, onset_precision=precision,
                        source_kind="firsthand")
        db.add(o)
        db.flush()
        obs_ids.append(o.id)

    # --- needs ---
    urgency = "today" if a.get("urgent") is True else "unknown"
    need_ids = []

    def add_need(category, people, qty, unit, supply="unknown"):
        n = Need(organization_id=org, report_id=report.id, area_id=area_id,
                 reporter_key_id=key.id, category=category, people_affected=people,
                 quantity=Decimal(str(qty)) if qty is not None else None,
                 unit=unit if qty is not None else None, remaining_supply=supply or "unknown",
                 stated_urgency=urgency, urgency_inputs={"urgent_answer": a.get("urgent")},
                 status="active", status_changed_at=now, last_confirmed_at=now)
        db.add(n)
        db.flush()
        need_ids.append(n.id)
        return n

    if a.get("need_drinking") is True:
        n = add_need("water_drinking", a.get("drinking_people"), a.get("drinking_liters"),
                     "liters", a.get("drinking_supply"))
        db.add(WaterNeedDetail(organization_id=org, need_id=n.id, intended_use="drinking",
                               people_to_serve=a.get("drinking_people")))
    if a.get("need_other") is True:
        n = add_need("water_other", a.get("other_people"), None, None)
        db.add(WaterNeedDetail(organization_id=org, need_id=n.id, intended_use="other",
                               people_to_serve=a.get("other_people")))
    if a.get("need_charging") is True:
        count = a.get("charging_count")
        n = add_need("charging", None, count, "devices")
        db.add(ChargingNeedDetail(organization_id=org, need_id=n.id))
        db.add(ChargingDeviceRequest(organization_id=org, need_id=n.id,
                                     device_type=a.get("charging_device") or "other",
                                     device_count=count or 1))

    # --- permissions (OPW-015): each purpose recorded, "no" too ---
    for purpose, field_ in _PERMS:
        decision = "granted" if a.get(field_) is True else "denied"
        current = list(db.scalars(select(Permission).where(
            Permission.organization_id == org,
            Permission.contact_endpoint_id == ctx.endpoint.id,
            Permission.purpose == purpose, Permission.withdrawn_at.is_(None))))
        if any(p.decision == decision for p in current):
            continue
        for p in current:
            p.withdrawn_at = now
        db.add(Permission(organization_id=org, reporter_key_id=key.id,
                          contact_endpoint_id=ctx.endpoint.id, purpose=purpose,
                          notice_version=profile.notice_version, processing_basis="consent",
                          decision=decision, captured_at=now,
                          evidence_reference=f"whatsapp:{evidence}"[:200]))

    # --- review tasks ---
    flags = set(state.get("flags", []))
    if a.get("urgent") is True and "urgent_task_created" not in flags:
        db.add(ReviewTask(organization_id=org, reason="urgent_flag", report_id=report.id,
                          area_id=area_id, reasons_json=["whatsapp_urgent_yes"],
                          due_at=now + timedelta(hours=4)))
    if "unparsed_text" in flags:
        db.add(ReviewTask(organization_id=org, reason="unparsed_text", report_id=report.id,
                          area_id=area_id, reasons_json=["whatsapp_free_text"]))
    if location_kind == "unresolved" or "unresolved_location" in flags:
        db.add(ReviewTask(organization_id=org, reason="unresolved_location",
                          report_id=report.id, reasons_json=["whatsapp_area_unmatched"]))
    db.flush()
    return PersistResult(report.id, old is not None, need_ids, obs_ids)
