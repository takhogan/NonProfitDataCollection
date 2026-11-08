"""In-memory fake data for STEP 1 (contract-first).

Deterministic, no DB. STEP 2 replaces reads here with real queries against the
shared database written by whatsapp/api. Shapes returned here ARE the contract —
keep them stable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# ---- Users / orgs (signup + login live here in step 1) --------------------
# email -> {password, user_id, org_id, org_name, role}
USERS: dict[str, dict] = {
    "demo@metron.org": {
        "password": "demo-pass",
        "user_id": "user-demo",
        "org_id": "org-demo",
        "org_name": "Miami Mutual Aid",
        "role": "org_admin",
    }
}

# org_id -> org profile / config blobs
ORG_PROFILE: dict[str, dict] = {
    "org-demo": {
        "name": "Miami Mutual Aid",
        "type": "community",
        "mission": "Coordinate power and water relief across Miami-Dade neighborhoods.",
        "region": "Miami-Dade, FL",
        "languages": ["en", "es", "ht"],
        "population_served": "Low-income and elderly residents in flood-prone areas",
        "team_size": 12,
    }
}

ORG_DATA_PROTECTION: dict[str, dict] = {
    "org-demo": {
        "preset": "standard",
        "store_names": True,
        "location_precision": "precise",
        "raw_message_retention_days": 90,
        "mask_phone_numbers": False,
        "redact_exports": False,
        "individual_records_roles": ["org_admin", "coordinator"],
        "audit_log_enabled": True,
    }
}

ORG_CHANNELS: dict[str, list] = {
    "org-demo": [
        {"channel": "whatsapp", "status": "connected", "identifier": "+1 305 555 0142",
         "mode": "shared_bot"},
        {"channel": "sms", "status": "disconnected", "identifier": None, "mode": "own_number"},
        {"channel": "telegram", "status": "disconnected", "identifier": None, "mode": "own_number"},
        {"channel": "email", "status": "disconnected", "identifier": None, "mode": "own_number"},
    ]
}

ORG_BOT_CONFIG: dict[str, dict] = {}
ORG_DASHBOARD_CONFIG: dict[str, dict] = {}


def _now() -> datetime:
    return datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)


MIAMI_AREAS = [
    "Little Haiti", "Liberty City", "Overtown", "Allapattah", "Wynwood",
    "Little Havana", "Hialeah", "Opa-locka", "Homestead", "Kendall",
]


def fake_feed(limit: int = 20) -> list[dict]:
    base = _now()
    items = []
    samples = [
        ("Little Haiti", "Sin luz desde anoche, 3 personas mayores en casa.",
         ["no_power", "elderly", "urgent"]),
        ("Liberty City", "No water since yesterday, need drinking water for kids.",
         ["no_water", "children"]),
        ("Overtown", "Power flickering on and off all morning.",
         ["intermittent_power"]),
        ("Allapattah", "Necesito cargar equipo médico, no hay electricidad.",
         ["no_power", "medical_device", "urgent"]),
        ("Hialeah", "Agua volvió pero huele raro, no sabemos si es potable.",
         ["water_quality"]),
    ]
    for i, (area, text, tags) in enumerate(samples[:limit]):
        items.append({
            "id": f"msg-{i+1}",
            "received_at": (base - timedelta(minutes=7 * (i + 1))).isoformat(),
            "area": area,
            "channel": "whatsapp",
            "preview": text,
            "tags": tags,
            "report_id": f"report-{i+1}",
        })
    return items


def fake_reports() -> list[dict]:
    base = _now()
    rows = []
    data = [
        ("report-1", "Little Haiti", "confirmed", True, ["no_power", "elderly"],
         "electricity", "unavailable"),
        ("report-2", "Liberty City", "confirmed", True, ["no_water", "children"],
         "piped_water", "unavailable"),
        ("report-3", "Overtown", "confirmed", False, ["intermittent_power"],
         "electricity", "intermittent"),
        ("report-4", "Allapattah", "confirmed", True, ["no_power", "medical_device"],
         "electricity", "unavailable"),
        ("report-5", "Hialeah", "review", False, ["water_quality"],
         "piped_water", "available"),
    ]
    for i, (rid, area, status, urgent, tags, svc, svc_status) in enumerate(data):
        rows.append({
            "id": rid,
            "area": area,
            "status": status,
            "urgent": urgent,
            "submitted_at": (base - timedelta(hours=i + 1)).isoformat(),
            "source_channel": "whatsapp",
            "service_type": svc,
            "service_status": svc_status,
            "tags": tags,
            # RAW PII — privacy filtering is applied at response time, not here.
            "reporter_name": ["Marie Pierre", "José Díaz", "Anonymous",
                              "Keisha Brown", "Luis Romero"][i % 5],
            "reporter_phone": f"+1305555{1000 + i:04d}",
            "notes": "",
            "assignee": None,
        })
    return rows


def fake_report_detail(report_id: str) -> dict | None:
    for r in fake_reports():
        if r["id"] == report_id:
            return {
                **r,
                "transcript": [
                    {"from": "reporter", "at": r["submitted_at"],
                     "text": "Hola, no tengo luz desde anoche."},
                    {"from": "bot", "at": r["submitted_at"],
                     "text": "Gracias. ¿Cuántas personas hay en casa?"},
                    {"from": "reporter", "at": r["submitted_at"], "text": "Somos 3."},
                ],
                "extracted_fields": {
                    "power_status": r["service_status"] if r["service_type"] == "electricity" else "unknown",
                    "water_status": r["service_status"] if r["service_type"] == "piped_water" else "unknown",
                    "household_size": 3,
                    "urgent_needs": r["tags"],
                    "days_without_water": 1 if "no_water" in r["tags"] else None,
                },
            }
    return None
