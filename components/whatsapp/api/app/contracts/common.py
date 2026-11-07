"""Shared contract schemas (auth, membership) used across routers."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    role: str
    status: str


class MeResponse(BaseModel):
    id: str
    auth_subject: str
    display_name: str
    memberships: list[MembershipOut]
