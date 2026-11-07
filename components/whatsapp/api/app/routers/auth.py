"""Authentication: exchange seeded credentials for a JWT bearer token."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.common import LoginRequest, TokenResponse
from app.db import get_db
from app.errors import PermissionDenied
from app.models.org import User
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.auth_subject == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise PermissionDenied("Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))
