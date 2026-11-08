"""Let the deployment's database login switch to the RLS group roles.

The pilot deployment uses one Cloud SQL login (``aid_app``) for migrations and
for the API and worker. ``app.db.tenant_transaction`` runs ``SET LOCAL ROLE
csl_worker`` (or ``csl_runtime``, ...) so row-level security and the role-aware
policies apply; that needs membership in those group roles. The login created
the roles in 2a7c4e91d3b0, so it holds ADMIN on them and can grant them to
itself. This does not widen what the login can do (it owns the tables); it only
lets it drop to the restricted roles.

Separate runtime logins (README "Database (pilot schema)") remain the target;
grant them the roles the same way when they exist.

Revision ID: 6b2d9e7a1c34
Revises: 5e8a1c2d4f60
Create Date: 2026-11-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "6b2d9e7a1c34"
down_revision: Union[str, None] = "5e8a1c2d4f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = "csl_runtime, csl_worker, csl_provider, csl_analyst, csl_public"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"GRANT {ROLES} TO CURRENT_USER")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"REVOKE {ROLES} FROM CURRENT_USER")
