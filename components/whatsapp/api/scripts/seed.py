"""Seed SYNTHETIC demo data for the pilot report-centric schema (DB-090).

Everything here is invented: organizations, people, phone numbers, places,
boundaries, and reports. Parish names are public administrative names of
Libertador (Caracas); their boundaries and all sectors are synthetic
rectangles. No real personal information.

Two organizations:

- ``luzviva`` - "Luz Viva (demo, protective)": protective profile, meeting
  points, no names/addresses/GPS.
- ``aguazul`` - "Agua Azul (demo, standard)": standard profile, encrypted
  names/addresses (placeholder ciphertext) and GPS points, household records.

Each has every role, three providers (two vetted, one unvetted) with scopes,
activities and alert subscriptions, the same synthetic Libertador geography
with meeting points, about 150 reports (about 300 total) covering shared
phones, repeat reporters, mixed permissions, unknown-coverage sectors, an
electricity outage spike, plus mock Monitor Ciudad external indicators.

    python -m scripts.seed

Skips if the demo organizations already exist. On PostgreSQL tenant rows are
written through ``tenant_transaction(..., role="system")`` so RLS applies.
"""
from __future__ import annotations

import hashlib
import hmac
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, tenant_transaction
from app.models import (
    Activity, ActivityArea, AlertSubscription, AlertSubscriptionArea, ApiKey, Area,
    AreaAlias, AreaBoundary, Campaign, CampaignArea, ChargingDeviceRequest, ContactEndpoint,
    ExternalIndicator, Household, MeetingPoint, Need, Observation, Organization,
    OrganizationMembership, Permission, PrivacyProfileVersion, ProviderOrganization,
    ProviderScope, QuestionnaireVersion, Report, ReporterKey, ReportLocation, ReviewTask, User,
    WaterNeedDetail,
)
from app.models.base import new_uuid
from app.security import hash_password

RNG_SEED = 20261107
# Dev-only HMAC key for synthetic lookup values. Real keys come from a managed
# secret service (DB-051); never reuse this.
_SYNTHETIC_HMAC_KEY = b"synthetic-seed-key-not-for-production"
_PLACEHOLDER = b"SYNTHETIC-PLACEHOLDER-NOT-ENCRYPTED:"

ORGS = {
    "luzviva": {"name": "Luz Viva (demo, protective)", "profile": "protective"},
    "aguazul": {"name": "Agua Azul (demo, standard)", "profile": "standard"},
}

# (email, display name, org key, role). Password comes from SEED_DEMO_PASSWORD.
# ana/luis/maria keep the logins documented in README.md.
USERS = [
    ("ana@aguazul.org", "Ana Rivas", "aguazul", "coordinator"),
    ("luis@aguazul.org", "Luis Peña", "aguazul", "intake_volunteer"),
    ("admin@aguazul.org", "Admin Agua Azul", "aguazul", "org_admin"),
    ("revisora@aguazul.org", "Revisora Agua Azul", "aguazul", "reviewer"),
    ("analista@aguazul.org", "Analista Agua Azul", "aguazul", "analyst"),
    ("maria@luzviva.org", "María Gómez", "luzviva", "coordinator"),
    ("admin@luzviva.org", "Admin Luz Viva", "luzviva", "org_admin"),
    ("revisor@luzviva.org", "Revisor Luz Viva", "luzviva", "reviewer"),
    ("voluntaria@luzviva.org", "Voluntaria Luz Viva", "luzviva", "intake_volunteer"),
    ("analista@luzviva.org", "Analista Luz Viva", "luzviva", "analyst"),
]

# (provider key, name, vetting status, categories, may disclose name)
PROVIDERS = [
    ("cisterna", "Cisternas Solidarias (demo)", "vetted", ("water_drinking", "water_other"), True),
    ("carga", "Punto de Carga Vecinal (demo)", "vetted", ("charging",), False),
    ("nuevo", "Brigada Nueva (demo)", "unvetted", ("water_drinking",), True),
]

# Synthetic geography: lon/lat boxes around central Caracas.
PARISHES = [
    ("Catedral", "CAT", -66.920, 10.500),
    ("San Juan", "SJU", -66.930, 10.490),
    ("Sucre", "SUC", -66.950, 10.510),
    ("23 de Enero", "23E", -66.940, 10.505),
]
SECTORS_PER_PARISH = 3
MP_KINDS = ("plaza", "church", "school", "bodega")

PROFILE_SETTINGS = {
    "protective": dict(
        names_allowed=False, location_mode="meeting_point", gps_allowed=False,
        household_records_allowed=False, contact_list_allowed=True,
        contact_list_fields=["alias", "sector", "meeting_point", "phone"],
        reporter_phone_retention_days=7, reporter_key_rotation_days=30,
        report_retention_days=548, aggregate_k=5, public_dashboard_enabled=False,
        public_level="parish", public_k=10, public_delay_hours=24,
    ),
    "standard": dict(
        names_allowed=True, location_mode="address", gps_allowed=True,
        household_records_allowed=True, contact_list_allowed=True,
        contact_list_fields=["name", "address", "phone"],
        reporter_phone_retention_days=548, reporter_key_rotation_days=90,
        report_retention_days=548, aggregate_k=3, public_dashboard_enabled=True,
        public_level="sector", public_k=5, public_delay_hours=6,
    ),
}


def _demo_password() -> str:
    """Demo password comes from SEED_DEMO_PASSWORD; never hardcoded.

    Required in production (validate_runtime enforces it); local dev falls back
    to a clearly non-secret value so `python -m scripts.seed` just works.
    """
    settings = get_settings()
    if settings.seed_demo_password:
        return settings.seed_demo_password
    if settings.is_production:
        raise RuntimeError("SEED_DEMO_PASSWORD must be set in production")
    return "local-demo-pass"


def _hmac(org_id: str, value: str) -> str:
    return hmac.new(_SYNTHETIC_HMAC_KEY, f"{org_id}|{value}".encode(), hashlib.sha256).hexdigest()


def _fake_cipher(text: str) -> bytes:
    return _PLACEHOLDER + text.encode()


def _box(lon: float, lat: float, w: float, h: float) -> str:
    x0, y0, x1, y1 = lon, lat, lon + w, lat + h
    return (f"SRID=4326;MULTIPOLYGON((({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0})))")


def _point(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon:.6f} {lat:.6f})"


# ---------------------------------------------------------------------------


def _seed_identity(db: Session) -> tuple[dict, dict]:
    """Organizations, users, memberships (identity tables, not RLS-secured)."""
    orgs: dict[str, Organization] = {}
    for key, spec in ORGS.items():
        org = Organization(name=spec["name"])
        db.add(org)
        orgs[key] = org
    db.flush()
    pw = hash_password(_demo_password())
    members: dict[str, OrganizationMembership] = {}
    for email, name, org_key, role in USERS:
        user = User(auth_subject=email, display_name=name, password_hash=pw)
        db.add(user)
        db.flush()
        m = OrganizationMembership(organization_id=orgs[org_key].id, user_id=user.id, role=role)
        db.add(m)
        db.flush()
        members[email] = m
    db.commit()
    return {k: o.id for k, o in orgs.items()}, {e: (m.id, m.user_id) for e, m in members.items()}


def _seed_geography(db: Session, org_id: str, rng: random.Random) -> dict:
    now = datetime.now(timezone.utc)
    state = Area(organization_id=org_id, type="state", name="Distrito Capital",
                 official_code="DC", source="synthetic")
    db.add(state)
    db.flush()
    muni = Area(organization_id=org_id, parent_area_id=state.id, type="municipality",
                name="Libertador", official_code="DC-LIB", source="synthetic")
    db.add(muni)
    db.flush()
    db.add(AreaBoundary(organization_id=org_id, area_id=muni.id, version=1,
                        boundary=_box(-66.96, 10.48, 0.06, 0.05), source="synthetic",
                        valid_from=now - timedelta(days=365)))
    parishes, sectors, meeting_points = [], [], {}
    for pname, code, lon, lat in PARISHES:
        p = Area(organization_id=org_id, parent_area_id=muni.id, type="parish", name=pname,
                 official_code=f"DC-LIB-{code}", source="synthetic boundary")
        db.add(p)
        db.flush()
        db.add(AreaBoundary(organization_id=org_id, area_id=p.id, version=1,
                            boundary=_box(lon, lat, 0.009, 0.003), source="synthetic",
                            valid_from=now - timedelta(days=365)))
        parishes.append(p)
        for i in range(SECTORS_PER_PARISH):
            s_lon = lon + i * 0.003
            s = Area(organization_id=org_id, parent_area_id=p.id, type="sector",
                     name=f"Sector {code}-{i + 1}", official_code=f"DC-LIB-{code}-S{i + 1}",
                     source="synthetic")
            db.add(s)
            db.flush()
            db.add(AreaBoundary(organization_id=org_id, area_id=s.id, version=1,
                                boundary=_box(s_lon, lat, 0.003, 0.003), source="synthetic",
                                valid_from=now - timedelta(days=365)))
            db.add(AreaAlias(organization_id=org_id, area_id=s.id, alias=f"{code} {i + 1}",
                             normalized_alias=f"{code.lower()} {i + 1}"))
            mps = []
            for j in range(2):
                kind = MP_KINDS[(i + j) % len(MP_KINDS)]
                mp = MeetingPoint(
                    organization_id=org_id, area_id=s.id,
                    name=f"{kind.capitalize()} {code}-{i + 1}{'ab'[j]} (demo)", kind=kind,
                    public_description=f"Punto público sintético frente a la {kind}.",
                    public_point=_point(s_lon + 0.001 + j * 0.001, lat + 0.0015),
                    status="active" if not (i == 2 and j == 1) else "inactive",
                )
                db.add(mp)
                mps.append(mp)
            db.flush()
            sectors.append((s, s_lon, lat))
            meeting_points[s.id] = [m for m in mps if m.status == "active"]
    return {"state": state, "muni": muni, "parishes": parishes, "sectors": sectors,
            "meeting_points": meeting_points}


def _seed_profile_and_campaign(db: Session, org_id: str, profile: str, admin_mid: str):
    now = datetime.now(timezone.utc)
    pv = PrivacyProfileVersion(
        organization_id=org_id, version=1, profile_key=profile, status="active",
        notice_version=f"{profile}-2026-11", activated_by_membership_id=admin_mid,
        activated_at=now - timedelta(days=30), **PROFILE_SETTINGS[profile],
    )
    qv = QuestionnaireVersion(organization_id=org_id, version=1, language="es",
                              definition_json={"synthetic": True, "steps": ["area", "services",
                                                                            "needs", "consent"]})
    db.add_all([pv, qv])
    db.flush()
    camp = Campaign(organization_id=org_id, name="Piloto Libertador (demo)",
                    display_identity="Metron Reporter", starts_at=now - timedelta(days=30),
                    status="active", questionnaire_version_id=qv.id)
    db.add(camp)
    db.flush()
    return pv, qv, camp


def _seed_providers(db: Session, org_id: str, org_key: str, geo: dict, rng: random.Random,
                    admin_mid: str, user_ids: list[str]) -> list:
    now = datetime.now(timezone.utc)
    pw = hash_password(_demo_password())
    sectors = [s for s, _, _ in geo["sectors"]]
    out = []
    for idx, (pkey, name, vetting, cats, disclose) in enumerate(PROVIDERS):
        po = ProviderOrganization(
            organization_id=org_id, name=name, vetting_status=vetting,
            vetting_reason="Synthetic vetting for demo" if vetting == "vetted" else None,
            vetting_changed_by_membership_id=admin_mid if vetting == "vetted" else None,
            vetting_changed_at=now - timedelta(days=20) if vetting == "vetted" else None,
            responsible_contact_reference=f"synthetic-contact-{pkey}",
            statement_version="2026-11" if vetting == "vetted" else None,
            may_disclose_name=disclose,
        )
        db.add(po)
        db.flush()
        user = User(auth_subject=f"{pkey}@{org_key}-provider.example", display_name=name,
                    password_hash=pw)
        db.add(user)
        db.flush()
        user_ids.append(user.id)
        mem = OrganizationMembership(organization_id=org_id, user_id=user.id, role="provider",
                                     provider_organization_id=po.id)
        db.add(mem)
        db.flush()
        # Scope: two parishes per provider (scope at parish level covers its sectors).
        scope_parishes = geo["parishes"][idx:idx + 2]
        for p in scope_parishes:
            for c in cats:
                db.add(ProviderScope(organization_id=org_id, provider_organization_id=po.id,
                                     area_id=p.id, category=c))
        # Activities: one active and one planned/paused/internal per provider.
        for k, (status, visibility) in enumerate((("active", "public"),
                                                  ("planned" if idx else "paused", "internal"))):
            cat = cats[0]
            act = Activity(
                organization_id=org_id, provider_organization_id=po.id,
                type={"water_drinking": "water_distribution_point", "water_other": "water_delivery",
                      "charging": "charging_point"}[cat],
                category=cat,
                schedule_json={"kind": "recurring", "days": ["sat"], "hours": [["08:00", "12:00"]],
                               "tz": "America/Caracas"},
                capacity=Decimal("2000") if cat.startswith("water") else Decimal("40"),
                capacity_unit="liters_per_day" if cat.startswith("water") else "devices_per_day",
                public_location_description="Punto público sintético",
                visibility=visibility, status=status,
                # One activity left unconfirmed (> 7 days).
                last_confirmed_at=now - timedelta(days=9 if (idx == 0 and k == 1) else 1),
                created_by_membership_id=mem.id,
            )
            db.add(act)
            db.flush()
            for s in rng.sample(sectors[idx * 3: idx * 3 + 6], 2):
                db.add(ActivityArea(organization_id=org_id, activity_id=act.id, area_id=s.id))
        sub = AlertSubscription(organization_id=org_id, membership_id=mem.id, category=cats[0],
                                trigger="active_needs_above" if idx != 1 else "new_urgent_needs",
                                threshold=10 if idx != 1 else None, channel="in_app")
        db.add(sub)
        db.flush()
        for p in scope_parishes:
            db.add(AlertSubscriptionArea(organization_id=org_id, alert_subscription_id=sub.id,
                                         area_id=p.id))
        if vetting == "vetted":
            db.add(ApiKey(organization_id=org_id, membership_id=mem.id,
                          provider_organization_id=po.id, name="demo key",
                          key_prefix=f"demo{idx}",
                          key_hash=hashlib.sha256(f"{org_id}-{pkey}-demo".encode()).hexdigest(),
                          scopes=["indicators:read", "coverage:read", "activities:write"],
                          expires_at=now + timedelta(days=90)))
        out.append(po)
    db.flush()
    return out


def _seed_reports(db: Session, org_id: str, profile: str, geo: dict, pv, qv, camp,
                  volunteer_mid: str, rng: random.Random) -> dict:
    """About 150 reports per org with the DB-090 scenarios."""
    now = datetime.now(timezone.utc)
    standard = profile == "standard"
    sectors = geo["sectors"]
    # Unknown coverage: the last sector of each of the last two parishes gets no reports.
    silent = {sectors[5][0].id, sectors[11][0].id}
    reporting = [s for s in sectors if s[0].id not in silent]
    spike_sector = reporting[0]

    # Contact endpoints / reporter keys. Some phones are shared.
    endpoints, keys = [], []
    for n in range(60):
        phone = f"+58-000-555-{n:04d}"  # synthetic, not a real numbering range
        ep = ContactEndpoint(organization_id=org_id, channel="whatsapp",
                             encrypted_address=_fake_cipher(phone),
                             address_lookup_hmac=_hmac(org_id, phone),
                             status="opted_out" if n % 23 == 22 else "active",
                             last_activity_at=now - timedelta(hours=rng.randint(1, 200)))
        endpoints.append(ep)
    db.add_all(endpoints)
    db.flush()
    for n, ep in enumerate(endpoints):
        k = ReporterKey(organization_id=org_id, key_hmac=_hmac(org_id, f"rk|{n}|epoch1"), epoch=1,
                        contact_endpoint_id=ep.id, alias=f"Vecino-{n:03X}",
                        expires_at=now + timedelta(days=30))
        keys.append(k)
    db.add_all(keys)
    db.flush()

    # Mixed permissions.
    stats = {"permissions": 0}
    for n, k in enumerate(keys):
        captured = now - timedelta(days=rng.randint(1, 20))
        grants = {"notice_ack": True, "refresh_prompts": n % 5 != 0,
                  "area_broadcasts": n % 3 == 0, "contact_list": n % 4 in (0, 1)}
        for purpose, granted in grants.items():
            withdrawn = captured + timedelta(days=1) if (purpose == "contact_list"
                                                         and n % 12 == 0) else None
            db.add(Permission(organization_id=org_id, reporter_key_id=k.id, purpose=purpose,
                              notice_version=pv.notice_version,
                              processing_basis="consent" if purpose != "notice_ack" else None,
                              decision="granted" if granted else "denied",
                              captured_at=captured, withdrawn_at=withdrawn))
            stats["permissions"] += 1

    # Shared phones (standard only): endpoints 0..4 each speak for 2-3 households.
    households: dict[int, list] = {}
    if standard:
        for n in range(5):
            hh = []
            for j in range(rng.randint(2, 3)):
                h = Household(organization_id=org_id, reference_code=f"AGU-SH-{n}-{j}",
                              estimated_member_count=rng.randint(1, 6))
                db.add(h)
                hh.append(h)
            households[n] = hh
        db.flush()

    plan = []  # (sector tuple, reporter index or None, hours ago, spike?)
    # Outage spike: 35 reports in the last 6 hours in one sector, electricity out.
    for i in range(35):
        plan.append((spike_sector, 20 + (i % 25), rng.uniform(0.2, 6), True))
    # Repeat reporters: keys 0..9 report 3-5 times each.
    for n in range(10):
        home = reporting[n % len(reporting)]
        for _ in range(rng.randint(3, 5)):
            plan.append((home, n, rng.uniform(1, 120), False))
    # Background reports up to ~150, a few anonymous area reports (no reporter key).
    while len(plan) < 150:
        sec = rng.choice(reporting[1:])
        idx = None if rng.random() < 0.08 else rng.randint(10, 59)
        plan.append((sec, idx, rng.uniform(1, 24 * 21), False))

    counts = {"reports": 0, "needs": 0, "observations": 0, "locations": 0}
    first_report_by_key: dict[int, Report] = {}
    for sec, kidx, hours_ago, spike in plan:
        area, s_lon, s_lat = sec
        submitted = now - timedelta(hours=hours_ago)
        status = "confirmed" if rng.random() > 0.06 else rng.choice(["draft", "abandoned"])
        mps = geo["meeting_points"][area.id]
        rk = keys[kidx] if kidx is not None else None
        if standard:
            location_kind = "address" if (rk is not None and rng.random() < 0.6) else "area_only"
            mp_id = None
        else:
            choice = rng.random()
            location_kind = "meeting_point" if choice < 0.7 else (
                "none_nearby" if choice < 0.85 else "area_only")
            mp_id = rng.choice(mps).id if location_kind == "meeting_point" else None
        hh = None
        if standard and kidx is not None and kidx in households:
            hh = rng.choice(households[kidx])
        via_volunteer = rng.random() < 0.1
        rep = Report(
            id=new_uuid(), organization_id=org_id, privacy_profile_version_id=pv.id,
            reporter_key_id=rk.id if rk else None, household_id=hh.id if hh else None,
            campaign_id=camp.id, questionnaire_version_id=qv.id,
            source_channel="volunteer_assisted" if via_volunteer else "whatsapp",
            reporting_relationship="area" if rk is None else rng.choice(
                ["self", "household", "household", "other_person"]),
            area_id=area.id, location_kind=location_kind, meeting_point_id=mp_id,
            encrypted_reporter_name=_fake_cipher(f"Nombre sintético {kidx}")
            if (standard and rk is not None and rng.random() < 0.5) else None,
            answers_json={"synthetic": True}, status=status, submitted_at=submitted,
            confirmed_at=submitted + timedelta(minutes=3) if status == "confirmed" else None,
            entered_by_membership_id=volunteer_mid if via_volunteer else None,
            urgent_flagged=spike and rng.random() < 0.1,
        )
        # Repeat reporter correction chain: occasionally supersede the first report.
        if kidx is not None and kidx < 10 and kidx in first_report_by_key and rng.random() < 0.15:
            prev = first_report_by_key.pop(kidx)
            if prev.status == "confirmed":
                rep.supersedes_report_id = prev.id
                prev.status = "superseded"
        elif kidx is not None and kidx < 10 and status == "confirmed":
            first_report_by_key.setdefault(kidx, rep)
        db.add(rep)
        db.flush()
        counts["reports"] += 1
        if standard and location_kind == "address":
            db.add(ReportLocation(
                organization_id=org_id, report_id=rep.id,
                encrypted_address=_fake_cipher(f"Calle sintética {rng.randint(1, 99)}"),
                restricted_point=_point(s_lon + rng.uniform(0, 0.003), s_lat + rng.uniform(0, 0.003))
                if rng.random() < 0.5 else None,
                accuracy_meters=rng.choice([10, 30, 100]), precision="street"))
            counts["locations"] += 1

        # Observations.
        for service in ("electricity", "piped_water"):
            if spike and service == "electricity":
                st = "unavailable"
            else:
                st = rng.choices(["available", "unavailable", "intermittent", "unknown"],
                                 [3, 3, 2, 1])[0]
            if not spike and rng.random() < 0.2:
                continue
            db.add(Observation(
                organization_id=org_id, report_id=rep.id, area_id=area.id, service_type=service,
                subject_scope="area" if rk is None else "household", status=st,
                observed_at=submitted - timedelta(minutes=10),
                observation_start_at=submitted - timedelta(hours=1),
                observation_end_at=submitted, time_precision="hour",
                outage_started_at=submitted - timedelta(hours=rng.randint(1, 30))
                if st == "unavailable" else None,
                onset_precision="part_of_day" if st == "unavailable" else None,
                source_kind="volunteer_observed" if via_volunteer else "firsthand"))
            counts["observations"] += 1

        # Needs (not for anonymous area reports).
        if rk is None:
            continue
        cats = []
        if spike:
            cats.append("charging")
        if rng.random() < 0.55:
            cats.append(rng.choice(["water_drinking", "water_drinking", "water_other"]))
        for cat in cats:
            age_h = hours_ago
            need_status = ("active" if age_h < 72 else "stale" if age_h < 14 * 24 else "expired")
            if rng.random() < 0.08:
                need_status = rng.choice(["resolved_by_reporter", "withdrawn"])
            water = cat.startswith("water")
            n = Need(
                organization_id=org_id, report_id=rep.id, category=cat,
                people_affected=None if rng.random() < 0.3 else rng.randint(1, 8),
                quantity=None if rng.random() < 0.3 else (
                    Decimal(str(rng.choice([20, 40, 60, 100]))) if water
                    else Decimal(rng.randint(1, 4))),
                unit="liters" if water else "devices",
                remaining_supply=rng.choice(["none", "little", "some", "unknown"]),
                stated_urgency=rng.choice(["today", "this_week", "can_wait", "unknown"]),
                access_flags={"cannot_leave_home": rng.random() < 0.15,
                              "no_containers": water and rng.random() < 0.2},
                status=need_status, status_changed_at=submitted,
                last_confirmed_at=submitted,
                refresh_prompt_count=0 if age_h < 72 else rng.randint(1, 3),
            )
            if n.quantity is None:
                n.unit = None
            db.add(n)
            db.flush()
            counts["needs"] += 1
            if water:
                db.add(WaterNeedDetail(organization_id=org_id, need_id=n.id,
                                       intended_use="drinking" if cat == "water_drinking"
                                       else "cooking_hygiene",
                                       people_to_serve=n.people_affected,
                                       has_containers=not n.access_flags["no_containers"]))
            else:
                db.add(ChargingDeviceRequest(organization_id=org_id, need_id=n.id,
                                             device_type=rng.choice(["phone", "phone", "lamp",
                                                                     "medical_device"]),
                                             device_count=int(n.quantity or 1)))
    db.flush()

    # Data-quality review tasks: the spike, an urgent flag, an unresolved location.
    db.add(ReviewTask(organization_id=org_id, reason="flood_or_burst", area_id=spike_sector[0].id,
                      reasons_json=["35 reports in 6h in one sector"], rule_version="v1"))
    flagged = db.execute(select(Report.id).where(Report.organization_id == org_id,
                                                 Report.urgent_flagged.is_(True))).scalars().first()
    if flagged:
        db.add(ReviewTask(organization_id=org_id, reason="urgent_flag", report_id=flagged))

    # Mock Monitor Ciudad external indicators (context layer only).
    for area, _, _ in reporting[:6]:
        db.add(ExternalIndicator(
            organization_id=org_id, area_id=area.id, source="monitor_ciudad_mock",
            source_label="Monitor Ciudad (mock, synthetic)", subject="electricity",
            indicator="outage_hours_24h", value=Decimal(str(rng.randint(0, 18))), unit="hours",
            observed_at=now - timedelta(hours=rng.randint(1, 12)),
            source_url="https://example.invalid/monitor-ciudad-mock"))
    db.flush()
    counts["unknown_coverage_sectors"] = len(silent)
    counts["spike_sector"] = spike_sector[0].name
    return counts


def _seed_tenant(org_key: str, org_id: str, members: dict, user_ids: list[str],
                 rng: random.Random, session_factory) -> dict:
    profile = ORGS[org_key]["profile"]
    by_role = {}
    for email, _, ok, role in USERS:
        if ok == org_key:
            by_role[role] = members[email][0]
    session = session_factory()
    with tenant_transaction(org_id, "seed", "system", session=session) as db:
        geo = _seed_geography(db, org_id, rng)
        pv, qv, camp = _seed_profile_and_campaign(db, org_id, profile, by_role["org_admin"])
        for p in geo["parishes"]:
            db.add(CampaignArea(organization_id=org_id, campaign_id=camp.id, area_id=p.id))
        providers = _seed_providers(db, org_id, org_key, geo, rng, by_role["org_admin"],
                                    user_ids)
        counts = _seed_reports(db, org_id, profile, geo, pv, qv, camp,
                               by_role["intake_volunteer"], rng)
        counts["providers"] = len(providers)
        counts["sectors"] = len(geo["sectors"])
    session.close()
    return counts


def seed(session_factory=SessionLocal) -> dict:
    db = session_factory()
    try:
        names = [spec["name"] for spec in ORGS.values()]
        if db.execute(select(Organization.id).where(Organization.name.in_(names))).first():
            print("Demo organizations already exist; skipping seed.")
            return {}
        org_ids, members = _seed_identity(db)
    finally:
        db.close()

    rng = random.Random(RNG_SEED)
    summary = {}
    provider_users: list[str] = []
    for key in ORGS:
        summary[key] = _seed_tenant(key, org_ids[key], members, provider_users, rng,
                                    session_factory)

    print("Seeded SYNTHETIC organizations:")
    for key, spec in ORGS.items():
        print(f"  - {spec['name']} ({org_ids[key]}): {summary[key]}")
    print("\nDemo logins (password from SEED_DEMO_PASSWORD):")
    for email, _, org_key, role in USERS:
        print(f"  - {email}  [{ORGS[org_key]['name']} / {role}]")
    print("  - <provider>@<org>-provider.example  [provider users, one per provider]")
    summary["org_ids"] = org_ids
    return summary


if __name__ == "__main__":
    seed()
