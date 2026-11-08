"""Request/response models for /v1 auth, me, and session admin routes.

They live here (not in app/contracts) only because of file ownership during
the parallel build; the contracts component can adopt them as-is.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class SignInStep(BaseModel):
    """Where the browser is in the sign-in flow. Keep csrf_token in memory only."""

    stage: Literal["totp_enroll", "totp_verify", "active"]
    csrf_token: str


class TotpEnrollment(BaseModel):
    secret: str
    otpauth_uri: str


class MembershipV1(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    role: str
    status: str


class SessionInfo(BaseModel):
    auth_method: str
    created_at: datetime
    expires_at: datetime
    idle_timeout_seconds: int


class MeV1(BaseModel):
    id: str
    email: str
    display_name: str
    active_organization_id: str | None
    role: str | None
    memberships: list[MembershipV1]
    # Filled once the provider and privacy-profile tables exist (DOM/DB work).
    provider_organization: dict | None = None
    vetting_status: str | None = None
    privacy_profile: dict | None = None
    auth_method: Literal["session", "dev_bearer"]
    session: SessionInfo | None = None
    # Send back as X-CSRF-Token on every cookie-authenticated mutation.
    csrf_token: str | None = None


class SetActiveOrganization(BaseModel):
    organization_id: str


class RevokeResult(BaseModel):
    revoked: int


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_method: str
    stage: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
