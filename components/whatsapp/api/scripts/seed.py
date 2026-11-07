"""Seed synthetic demo data: 2 organizations, a few users, sample households.

All people and contact details are synthetic (see repo README: do not commit
real personal information). Run after migrations:

    python -m scripts.seed

Idempotent-ish: it skips seeding if the organizations already exist.
"""
from __future__ import annotations

from app.config import get_settings
from app.context import RequestContext
from app.db import SessionLocal
from app.contracts.household import AssistedIntakeRequest, NeedIn, ObservationIn, PersonIn
from app.domain.intake import create_assisted_intake
from app.models.org import Organization, OrganizationMembership, User
from app.security import hash_password


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


# (email, display_name, org_key, role) — password is injected from env.
USERS = [
    ("ana@aguazul.org", "Ana Rivas", "aguazul", "coordinator"),
    ("luis@aguazul.org", "Luis Peña", "aguazul", "caseworker"),
    ("maria@luzviva.org", "María Gómez", "luzviva", "coordinator"),
]

ORGS = {
    "aguazul": "Agua Azul",  # water-focused NGO
    "luzviva": "Luz Viva",   # charging-focused NGO
}


def _seed_household(db, ctx: RequestContext, ref: str, contacts, observations, needs):
    req = AssistedIntakeRequest(
        reference_code=ref,
        estimated_member_count=len(contacts) + 1,
        contacts=[PersonIn(**c) for c in contacts],
        source_channel="volunteer_assisted",
        reporting_relationship="household",
        answers={"note": "synthetic demo data"},
        observations=[ObservationIn(**o) for o in observations],
        needs=[NeedIn(**n) for n in needs],
    )
    return create_assisted_intake(ctx, db, req)


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(Organization).count() > 0:
            print("Organizations already exist; skipping seed.")
            return

        orgs: dict[str, Organization] = {}
        for key, name in ORGS.items():
            org = Organization(name=name)
            db.add(org)
            orgs[key] = org
        db.flush()

        demo_password = _demo_password()
        memberships: dict[str, OrganizationMembership] = {}
        for email, name, org_key, role in USERS:
            user = User(
                auth_subject=email, display_name=name,
                password_hash=hash_password(demo_password),
            )
            db.add(user)
            db.flush()
            mem = OrganizationMembership(
                organization_id=orgs[org_key].id, user_id=user.id, role=role
            )
            db.add(mem)
            db.flush()
            memberships[email] = mem
        db.commit()

        # Sample households per org, via the real intake command.
        ctx_ana = RequestContext(
            org_id=orgs["aguazul"].id, actor_id=memberships["ana@aguazul.org"].user_id,
            membership_id=memberships["ana@aguazul.org"].id, role="coordinator",
        )
        _seed_household(
            db, ctx_ana, "AGU-001",
            contacts=[{"preferred_name": "Carmen", "preferred_language": "es",
                       "relationship_label": "head"}],
            observations=[{"service_type": "piped_water", "status": "unavailable"}],
            needs=[{"category": "water_delivery", "requested_quantity": 40,
                    "unit": "liters", "urgency": "urgent"}],
        )
        _seed_household(
            db, ctx_ana, "AGU-002",
            contacts=[{"preferred_name": "José", "preferred_language": "es"}],
            observations=[{"service_type": "piped_water", "status": "intermittent"},
                          {"service_type": "electricity", "status": "unavailable"}],
            needs=[{"category": "water_delivery", "requested_quantity": 20, "unit": "liters"},
                   {"category": "charging_access", "requested_quantity": 1,
                    "unit": "device_sessions"}],
        )

        ctx_maria = RequestContext(
            org_id=orgs["luzviva"].id, actor_id=memberships["maria@luzviva.org"].user_id,
            membership_id=memberships["maria@luzviva.org"].id, role="coordinator",
        )
        _seed_household(
            db, ctx_maria, "LUZ-001",
            contacts=[{"preferred_name": "Rosa", "preferred_language": "es"}],
            observations=[{"service_type": "electricity", "status": "unavailable"}],
            needs=[{"category": "charging_access", "requested_quantity": 3,
                    "unit": "device_sessions", "urgency": "routine"}],
        )

        print("Seeded organizations:")
        for key, org in orgs.items():
            print(f"  - {org.name} ({org.id})")
        print("\nDemo logins (password from SEED_DEMO_PASSWORD):")
        for email, name, org_key, role in USERS:
            print(f"  - {email}  [{ORGS[org_key]} / {role}]")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
