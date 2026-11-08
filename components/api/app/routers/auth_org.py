"""Auth, current user, org profile/onboarding, data-protection, channels, contacts.

STEP 1: returns realistic fake data from app.fakestore. Shapes are the contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile

from app.context import RequestContext, resolve_data_protection
from app.deps import get_context
from app.errors import Conflict, PermissionDenied
from app.fakestore import (
    ORG_BOT_CONFIG, ORG_CHANNELS, ORG_DASHBOARD_CONFIG, ORG_DATA_PROTECTION,
    ORG_PROFILE, USERS,
)
from app.security import create_access_token
from app import schemas as S

router = APIRouter(tags=["auth-org"])


# ---- Auth ------------------------------------------------------------------

@router.post("/auth/signup", response_model=S.TokenResponse)
def signup(body: S.SignupRequest) -> S.TokenResponse:
    if body.email in USERS:
        raise Conflict("email already registered")
    user_id = f"user-{len(USERS) + 1}"
    org_id = f"org-{len(USERS) + 1}"
    USERS[body.email] = {
        "password": body.password, "user_id": user_id, "org_id": org_id,
        "org_name": body.org_name, "role": "org_admin",
    }
    ORG_PROFILE[org_id] = {
        "name": body.org_name, "type": body.org_type, "mission": "", "region": "",
        "languages": [], "population_served": "", "team_size": None,
    }
    ORG_DATA_PROTECTION[org_id] = dict(ORG_DATA_PROTECTION["org-demo"])
    ORG_CHANNELS[org_id] = [dict(c) for c in ORG_CHANNELS["org-demo"]]
    return S.TokenResponse(access_token=create_access_token(user_id))


@router.post("/auth/login", response_model=S.TokenResponse)
def login(body: S.LoginRequest) -> S.TokenResponse:
    rec = USERS.get(body.email)
    if rec is None or rec["password"] != body.password:
        raise PermissionDenied("Invalid credentials")
    return S.TokenResponse(access_token=create_access_token(rec["user_id"]))


@router.get("/me", response_model=S.MeResponse)
def me(ctx: RequestContext = Depends(get_context)) -> S.MeResponse:
    email = next((e for e, r in USERS.items() if r["user_id"] == ctx.actor_id), "")
    return S.MeResponse(
        id=ctx.actor_id, email=email, display_name=ctx.org_name and "" or "",
        memberships=[S.MembershipOut(
            organization_id=ctx.org_id, organization_name=ctx.org_name, role=ctx.role,
        )],
    )


# ---- Org profile / onboarding ----------------------------------------------

@router.get("/org/profile", response_model=S.OrgProfile)
def get_org_profile(ctx: RequestContext = Depends(get_context)) -> S.OrgProfile:
    return S.OrgProfile(**ORG_PROFILE[ctx.org_id])


@router.put("/org/profile", response_model=S.OrgProfile)
def put_org_profile(body: S.OrgProfile, ctx: RequestContext = Depends(get_context)) -> S.OrgProfile:
    ORG_PROFILE[ctx.org_id] = body.model_dump()
    return body


@router.get("/templates/collection", response_model=list[S.CollectionTemplate])
def collection_templates(ctx: RequestContext = Depends(get_context)) -> list[S.CollectionTemplate]:
    return _COLLECTION_TEMPLATES


@router.get("/templates/collection/recommended", response_model=S.RecommendedTemplates)
def recommended_templates(ctx: RequestContext = Depends(get_context)) -> S.RecommendedTemplates:
    # Simple rule from the org profile (fake): outage-focused orgs get power/water.
    profile = ORG_PROFILE.get(ctx.org_id, {})
    ids = ["power_water_outages"]
    if "elderly" in (profile.get("population_served", "").lower()):
        ids.append("elderly_check_ins")
    return S.RecommendedTemplates(
        recommended_collection_ids=ids,
        reason="Based on your region and population served (outage-prone, elderly residents).",
    )


@router.get("/templates/dashboard", response_model=list[S.DashboardTemplate])
def dashboard_templates(ctx: RequestContext = Depends(get_context)) -> list[S.DashboardTemplate]:
    return _DASHBOARD_TEMPLATES


@router.put("/org/bot-config", response_model=S.BotConfig)
def put_bot_config(body: S.BotConfig, ctx: RequestContext = Depends(get_context)) -> S.BotConfig:
    ORG_BOT_CONFIG[ctx.org_id] = body.model_dump()
    return body


@router.put("/org/dashboard-config", response_model=S.DashboardConfig)
def put_dashboard_config(body: S.DashboardConfig, ctx: RequestContext = Depends(get_context)) -> S.DashboardConfig:
    ORG_DASHBOARD_CONFIG[ctx.org_id] = body.model_dump()
    return body


# ---- Data protection -------------------------------------------------------

@router.get("/org/data-protection", response_model=S.DataProtectionConfig)
def get_data_protection(ctx: RequestContext = Depends(get_context)) -> S.DataProtectionConfig:
    # Return the RESOLVED settings (preset flags applied) so the UI shows what the
    # preset actually enforces, matching what the API does to responses.
    dp = resolve_data_protection(ORG_DATA_PROTECTION[ctx.org_id])
    return S.DataProtectionConfig(
        preset=dp.preset, store_names=dp.store_names,
        location_precision=dp.location_precision,
        raw_message_retention_days=dp.raw_message_retention_days,
        mask_phone_numbers=dp.mask_phone_numbers, redact_exports=dp.redact_exports,
        individual_records_roles=list(dp.individual_records_roles),
        audit_log_enabled=dp.audit_log_enabled,
        hide_individual_records=dp.hide_individual_records,
    )


@router.put("/org/data-protection", response_model=S.DataProtectionConfig)
def put_data_protection(body: S.DataProtectionConfig, ctx: RequestContext = Depends(get_context)) -> S.DataProtectionConfig:
    ORG_DATA_PROTECTION[ctx.org_id] = body.model_dump()
    return body


# ---- Channels --------------------------------------------------------------

@router.get("/org/channels", response_model=S.ChannelsConfig)
def get_channels(ctx: RequestContext = Depends(get_context)) -> S.ChannelsConfig:
    return S.ChannelsConfig(channels=[S.Channel(**c) for c in ORG_CHANNELS[ctx.org_id]])


@router.put("/org/channels", response_model=S.ChannelsConfig)
def put_channels(body: S.ChannelsConfig, ctx: RequestContext = Depends(get_context)) -> S.ChannelsConfig:
    ORG_CHANNELS[ctx.org_id] = [c.model_dump() for c in body.channels]
    return body


# ---- Contacts --------------------------------------------------------------

@router.post("/contacts/import", response_model=S.ContactImportResult)
async def import_contacts(file: UploadFile, ctx: RequestContext = Depends(get_context)) -> S.ContactImportResult:
    raw = (await file.read()).decode("utf-8", "replace")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    data_rows = max(0, len(lines) - 1)  # minus header
    return S.ContactImportResult(imported=data_rows, skipped=0, errors=[])


@router.get("/contacts", response_model=list[S.Contact])
def list_contacts(ctx: RequestContext = Depends(get_context)) -> list[S.Contact]:
    dp = ctx.data_protection
    # `minimal` preset exposes aggregates only — no individual contact records.
    if dp.hide_individual_records:
        return []
    raw = [
        {"id": "c1", "name": "Marie Pierre", "phone": "+13055550142",
         "area": "Little Haiti", "consent_status": "granted", "last_contact_at": None},
        {"id": "c2", "name": "José Díaz", "phone": "+13055550199",
         "area": "Hialeah", "consent_status": "pending", "last_contact_at": None},
    ]
    out = []
    for c in raw:
        out.append(S.Contact(
            id=c["id"],
            name=dp.apply_name(c["name"]),
            phone=dp.apply_phone(c["phone"]),
            area=c["area"],
            consent_status=c["consent_status"],
            last_contact_at=c["last_contact_at"],
        ))
    return out


# ---- Template data (fake) --------------------------------------------------

def _q(key, label, ftype, options=None):
    return S.TemplateQuestion(key=key, label=label, field_type=ftype, options=options)


_COLLECTION_TEMPLATES = [
    S.CollectionTemplate(
        id="power_water_outages", name="Power & Water Outages",
        description="Track electricity and piped-water status and needs.",
        questions=[
            _q("power_status", "¿Cómo está la electricidad?", "choice",
               ["available", "unavailable", "intermittent", "unknown"]),
            _q("water_status", "¿Cómo está el agua?", "choice",
               ["available", "unavailable", "intermittent", "unknown"]),
            _q("household_size", "¿Cuántas personas hay en casa?", "number"),
            _q("urgent_needs", "¿Hay una necesidad urgente?", "text"),
        ],
        fields=["power_status", "water_status", "household_size", "urgent_needs", "area"],
    ),
    S.CollectionTemplate(
        id="food_security", name="Food Security",
        description="Assess food access and shortages.",
        questions=[
            _q("days_of_food", "¿Para cuántos días tiene comida?", "number"),
            _q("children_in_home", "¿Hay niños en el hogar?", "boolean"),
        ],
        fields=["days_of_food", "children_in_home", "area"],
    ),
    S.CollectionTemplate(
        id="elderly_check_ins", name="Elderly Check-ins",
        description="Periodic wellness checks for elderly residents.",
        questions=[
            _q("is_safe", "¿Está bien y a salvo?", "boolean"),
            _q("medication_needs", "¿Necesita medicamentos?", "text"),
        ],
        fields=["is_safe", "medication_needs", "area"],
    ),
    S.CollectionTemplate(
        id="disaster_needs", name="Disaster Needs",
        description="Rapid needs assessment after a disaster.",
        questions=[
            _q("shelter_status", "¿Tiene refugio seguro?", "choice",
               ["safe", "damaged", "displaced", "unknown"]),
            _q("immediate_needs", "¿Qué necesita de inmediato?", "text"),
        ],
        fields=["shelter_status", "immediate_needs", "area"],
    ),
    S.CollectionTemplate(
        id="beneficiary_feedback", name="Beneficiary Feedback",
        description="Collect feedback on assistance received.",
        questions=[
            _q("received_help", "¿Recibió la ayuda?", "boolean"),
            _q("satisfaction", "¿Qué tan satisfecho está?", "choice",
               ["very", "somewhat", "not"]),
        ],
        fields=["received_help", "satisfaction"],
    ),
    S.CollectionTemplate(
        id="aid_confirmation", name="Grant / Aid Confirmation",
        description="Confirm aid or grant delivery.",
        questions=[
            _q("aid_received", "¿Confirmó la entrega?", "boolean"),
            _q("amount", "¿Qué cantidad/valor recibió?", "text"),
        ],
        fields=["aid_received", "amount"],
    ),
]

_DASHBOARD_TEMPLATES = [
    S.DashboardTemplate(
        id="needs_overview", name="Needs Overview", recommended=True,
        description="Summary metrics, area breakdown, and a live feed.",
        widgets=[
            S.DashboardWidget(key="summary", label="AI Summary", type="metric"),
            S.DashboardWidget(key="metrics", label="Key Metrics", type="metric"),
            S.DashboardWidget(key="areas", label="By Neighborhood", type="list"),
            S.DashboardWidget(key="feed", label="Live Feed", type="feed"),
        ],
    ),
    S.DashboardTemplate(
        id="map_first", name="Map-first",
        description="Geographic view of reports and needs.",
        widgets=[
            S.DashboardWidget(key="map", label="Needs Map", type="map"),
            S.DashboardWidget(key="areas", label="Area Counts", type="list"),
        ],
    ),
    S.DashboardTemplate(
        id="case_management", name="Case Management",
        description="Work the report queue by status and assignee.",
        widgets=[
            S.DashboardWidget(key="reports", label="Report Queue", type="list"),
            S.DashboardWidget(key="metrics", label="Workload", type="metric"),
        ],
    ),
]
