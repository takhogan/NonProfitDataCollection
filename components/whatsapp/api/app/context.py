"""Request context passed explicitly into domain functions.

Domain code receives (ctx, db, ...) and must scope every query to ctx.org_id.
The org_id is derived from the authenticated user's memberships, never from a
client-supplied request field.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    org_id: str
    actor_id: str  # the authenticated user id (actor), for audit/assignment
    membership_id: str
    role: str
