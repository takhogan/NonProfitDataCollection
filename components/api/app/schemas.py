"""Pydantic request/response models — the stable frontend contract.

Report-centric (cases are deferred in the pilot). Org always derived from the
JWT; never a body field.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---- Auth ------------------------------------------------------------------

OrgType = Literal["NGO", "NPO", "community", "foundation", "other"]


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    org_name: str
    org_type: OrgType = "community"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MembershipOut(BaseModel):
    organization_id: str
    organization_name: str
    role: str


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    memberships: list[MembershipOut]


# ---- Org profile / onboarding ----------------------------------------------

class OrgProfile(BaseModel):
    name: str
    type: OrgType
    mission: str = ""
    region: str = ""
    languages: list[str] = Field(default_factory=list)
    population_served: str = ""
    team_size: int | None = None


class TemplateQuestion(BaseModel):
    key: str
    label: str
    field_type: Literal["text", "choice", "number", "boolean", "location"]
    options: list[str] | None = None


class CollectionTemplate(BaseModel):
    id: str
    name: str
    description: str
    questions: list[TemplateQuestion]
    fields: list[str]


class DashboardWidget(BaseModel):
    key: str
    label: str
    type: Literal["metric", "map", "feed", "list", "chart"]


class DashboardTemplate(BaseModel):
    id: str
    name: str
    description: str
    widgets: list[DashboardWidget]
    recommended: bool = False


class RecommendedTemplates(BaseModel):
    recommended_collection_ids: list[str]
    reason: str


class BotConfig(BaseModel):
    greeting: str = ""
    language_default: str = "es"
    collection_template_id: str | None = None
    ask_consent: bool = True
    human_handoff_enabled: bool = True


class DashboardConfig(BaseModel):
    template_id: str
    widgets: list[str] = Field(default_factory=list)


# ---- Data protection -------------------------------------------------------

class DataProtectionConfig(BaseModel):
    preset: Literal["standard", "protected", "minimal", "custom"] = "standard"
    store_names: bool = True
    location_precision: Literal["area", "precise"] = "precise"
    raw_message_retention_days: int = 90
    mask_phone_numbers: bool = False
    redact_exports: bool = False
    individual_records_roles: list[str] = Field(default_factory=list)
    audit_log_enabled: bool = True
    # Set by the `minimal` preset: individual records are hidden (aggregates only).
    hide_individual_records: bool = False


# ---- Channels --------------------------------------------------------------

class Channel(BaseModel):
    channel: Literal["whatsapp", "sms", "telegram", "email"]
    status: Literal["connected", "disconnected", "pending"]
    identifier: str | None = None
    mode: Literal["shared_bot", "own_number"] = "own_number"


class ChannelsConfig(BaseModel):
    channels: list[Channel]


# ---- Contacts --------------------------------------------------------------

class ContactImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


class Contact(BaseModel):
    id: str
    name: str | None = None          # None when names are not stored
    phone: str | None = None         # masked per data-protection
    area: str | None = None
    consent_status: Literal["granted", "pending", "declined", "unknown"]
    last_contact_at: str | None = None


# ---- Dashboard -------------------------------------------------------------

class DashboardMetrics(BaseModel):
    reports_today: int
    without_power: int
    without_water: int
    urgent: int


class DashboardSummary(BaseModel):
    summary: str                     # AI sentence
    metrics: DashboardMetrics
    generated_at: str


class AreaCount(BaseModel):
    area: str
    reports: int
    without_power: int
    without_water: int
    urgent: int


class FeedItem(BaseModel):
    id: str
    received_at: str
    area: str | None
    channel: str
    preview: str
    tags: list[str]
    report_id: str | None = None


class FeedResponse(BaseModel):
    items: list[FeedItem]
    cursor: str | None = None        # pass back as ?since= to poll


# ---- Reports (report-centric; replaces cases) ------------------------------

ReportStatus = Literal["draft", "confirmed", "review", "superseded", "withdrawn"]


class ReportSummary(BaseModel):
    id: str
    area: str | None
    status: str
    urgent: bool
    submitted_at: str
    source_channel: str
    service_type: str | None = None
    service_status: str | None = None
    tags: list[str] = Field(default_factory=list)
    reporter_name: str | None = None     # masked/omitted per privacy
    reporter_phone: str | None = None    # masked per privacy
    assignee: str | None = None


class TranscriptLine(BaseModel):
    from_: str = Field(alias="from")
    at: str
    text: str

    model_config = {"populate_by_name": True}


class ReportDetail(ReportSummary):
    notes: str = ""
    transcript: list[TranscriptLine] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)


class ReportPatch(BaseModel):
    status: ReportStatus | None = None
    notes: str | None = None
    assignee: str | None = None


# ---- Campaigns -------------------------------------------------------------

class CampaignCreate(BaseModel):
    name: str
    collection_template_id: str
    areas: list[str] = Field(default_factory=list)
    starts_at: str | None = None
    ends_at: str | None = None


class Campaign(BaseModel):
    id: str
    name: str
    collection_template_id: str
    areas: list[str]
    status: str
    starts_at: str | None = None
    ends_at: str | None = None


# ---- Ask (NL question) -----------------------------------------------------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    data: dict[str, Any] = Field(default_factory=dict)
