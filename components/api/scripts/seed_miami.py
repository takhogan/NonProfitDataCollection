"""Seed ~80 synthetic Miami-area outage reports into the SHARED database so the
dashboard looks full for the demo.

Creates (idempotently): a demo organization "Miami Mutual Aid", a demo user
(demo@metron.org), an active privacy profile, Miami-area `area` rows, and ~80
reports with observations (power/water) and some needs — a handful flagged
urgent. Everything is synthetic.

Run with the dashboard venv (it bridges to whatsapp/api's models):

    DATABASE_URL="sqlite:///../whatsapp/api/local-data/aid.sqlite3" \
      .venv/bin/python -m scripts.seed_miami
"""
from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the dashboard package and whatsapp/api importable.
_HERE = Path(__file__).resolve().parent.parent          # components/api
sys.path.insert(0, str(_HERE))
from dash.shared_db import models, get_sessionmaker      # noqa: E402
import app.security as intake_security                   # noqa: E402

SEED = 20261108
DEMO_EMAIL = "demo@metron.org"
DEMO_PASSWORD = os.environ.get("SEED_DEMO_PASSWORD", "demo-pass")
ORG_NAME = "Miami Mutual Aid"

MIAMI_AREAS = [
    "Little Haiti", "Liberty City", "Overtown", "Allapattah", "Wynwood",
    "Little Havana", "Hialeah", "Opa-locka", "Homestead", "Kendall",
]

POWER_STATES = ["unavailable", "intermittent", "available", "unknown"]
WATER_STATES = ["unavailable", "intermittent", "available", "unknown"]
SUMMARIES = [
    "Sin luz desde anoche.", "No water since yesterday.",
    "Power flickering all morning.", "Necesito cargar equipo médico.",
    "Agua volvió pero huele raro.", "Vecindario entero sin electricidad.",
    "Elderly neighbor needs drinking water.", "Generator out of fuel.",
]


def _now() -> datetime:
    return datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)


def seed() -> None:
    rng = random.Random(SEED)
    db = get_sessionmaker()()
    try:
        # Org (idempotent by name).
        org = db.query(models.Organization).filter_by(name=ORG_NAME).one_or_none()
        if org is None:
            org = models.Organization(name=ORG_NAME, status="active")
            db.add(org); db.flush()

        # Demo user + membership.
        user = db.query(models.User).filter_by(auth_subject=DEMO_EMAIL).one_or_none()
        if user is None:
            user = models.User(auth_subject=DEMO_EMAIL, display_name="Demo Admin",
                               password_hash=intake_security.hash_password(DEMO_PASSWORD))
            db.add(user); db.flush()
        mem = (db.query(models.OrganizationMembership)
                 .filter_by(organization_id=org.id, user_id=user.id).one_or_none())
        if mem is None:
            mem = models.OrganizationMembership(organization_id=org.id, user_id=user.id,
                                                role="org_admin", status="active")
            db.add(mem); db.flush()

        # Active privacy profile (standard) — required FK on reports.
        prof = (db.query(models.PrivacyProfileVersion)
                  .filter_by(organization_id=org.id, status="active").one_or_none())
        if prof is None:
            prof = models.PrivacyProfileVersion(
                organization_id=org.id, version=1, profile_key="standard", status="active",
                names_allowed=True, location_mode="address", gps_allowed=True,
                household_records_allowed=True, contact_list_allowed=True,
                contact_list_fields=["name", "address", "phone"],
                reporter_phone_retention_days=548, reporter_key_rotation_days=90,
                report_retention_days=548, aggregate_k=3, public_dashboard_enabled=True,
                public_level="sector", public_k=5, public_delay_hours=6,
                notice_version="v1", activated_at=_now(),
            )
            db.add(prof); db.flush()

        # Areas (idempotent by name within org).
        area_ids: dict[str, str] = {}
        for name in MIAMI_AREAS:
            a = (db.query(models.Area)
                   .filter_by(organization_id=org.id, name=name).one_or_none())
            if a is None:
                a = models.Area(organization_id=org.id, type="sector", name=name,
                                source="synthetic")
                db.add(a); db.flush()
            area_ids[name] = a.id

        # If reports already seeded, stop (idempotent).
        existing = db.query(models.Report).filter_by(organization_id=org.id).count()
        if existing >= 80:
            print(f"already seeded ({existing} reports); skipping")
            db.commit()
            return

        urgent_quota = 12
        made_urgent = 0
        for i in range(80):
            area_name = rng.choice(MIAMI_AREAS)
            area_id = area_ids[area_name]
            submitted = _now() - timedelta(hours=rng.randint(0, 36), minutes=rng.randint(0, 59))
            power = rng.choices(POWER_STATES, weights=[5, 3, 2, 1])[0]
            water = rng.choices(WATER_STATES, weights=[3, 2, 4, 1])[0]
            is_urgent = made_urgent < urgent_quota and rng.random() < 0.2
            if is_urgent:
                made_urgent += 1

            report = models.Report(
                organization_id=org.id, privacy_profile_version_id=prof.id,
                source_channel="whatsapp", reporting_relationship="self",
                area_id=area_id, location_kind="area_only",
                answers_json={"summary": rng.choice(SUMMARIES),
                              "household_size": rng.randint(1, 7)},
                status="confirmed", submitted_at=submitted, confirmed_at=submitted,
                urgent_flagged=is_urgent,
            )
            db.add(report); db.flush()

            # Observations for the services that aren't "available".
            for svc, status in (("electricity", power), ("piped_water", water)):
                db.add(models.Observation(
                    organization_id=org.id, report_id=report.id, area_id=area_id,
                    service_type=svc, subject_scope="household", status=status,
                    observed_at=submitted, time_precision="hour",
                    reported_timezone="America/New_York", source_kind="firsthand",
                ))

            # A need if power/water is out.
            if power in ("unavailable", "intermittent"):
                db.add(models.Need(
                    organization_id=org.id, report_id=report.id, area_id=area_id,
                    category="charging", unit="devices", quantity=rng.randint(1, 3),
                    stated_urgency="today" if is_urgent else "this_week", status="active",
                ))
            if water in ("unavailable", "intermittent"):
                db.add(models.Need(
                    organization_id=org.id, report_id=report.id, area_id=area_id,
                    category="water_drinking", unit="liters", quantity=rng.randint(10, 40),
                    stated_urgency="today" if is_urgent else "this_week", status="active",
                ))

        db.commit()
        total = db.query(models.Report).filter_by(organization_id=org.id).count()
        print(f"Seeded org '{ORG_NAME}' ({org.id})")
        print(f"  demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"  reports: {total}, urgent: {made_urgent}, areas: {len(area_ids)}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
