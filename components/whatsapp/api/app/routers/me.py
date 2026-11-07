"""Current user and authorized organization memberships."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.contracts.common import MeResponse, MembershipOut
from app.deps import get_current_user
from app.models.org import User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse)
def read_me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        auth_subject=user.auth_subject,
        display_name=user.display_name,
        memberships=[MembershipOut.model_validate(m) for m in user.memberships],
    )
