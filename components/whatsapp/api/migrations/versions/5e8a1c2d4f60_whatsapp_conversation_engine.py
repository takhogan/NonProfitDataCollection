"""WhatsApp conversation engine: channel accounts, conversation state, outbox fields.

- ``channel_account`` maps a Meta ``phone_number_id`` to the organization (and
  campaign) that owns it. It is read before any tenant context exists, so it is
  not row-level secured; runtime roles may only SELECT it.
- ``conversation.state_json`` holds the questionnaire state machine (current
  step, answers so far, history for "Atrás"). Sensitive answers inside it are
  app-encrypted.
- ``outbox_message`` gains ``message_json`` (the rendered message), ``priority``
  (OPW-034), ``last_error`` and a provider-message-id index for status matching.

Revision ID: 5e8a1c2d4f60
Revises: 2a7c4e91d3b0
Create Date: 2026-11-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5e8a1c2d4f60"
down_revision: Union[str, None] = "2a7c4e91d3b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json(pg: bool):
    return postgresql.JSONB() if pg else sa.JSON()


def upgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"

    op.create_table(
        "channel_account",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("phone_number_id", sa.String(128), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organization.id"),
                  nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("phone_number_id", name="uq_channel_account_phone_number_id"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_channel_account_status"),
    )

    with op.batch_alter_table("conversation") as b:
        b.add_column(sa.Column("state_json", _json(pg), nullable=False,
                               server_default=sa.text("'{}'")))

    with op.batch_alter_table("outbox_message") as b:
        b.add_column(sa.Column("message_json", _json(pg), nullable=False,
                               server_default=sa.text("'{}'")))
        b.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index("ix_outbox_provider_message", "outbox_message",
                    ["provider_message_id"])

    if pg:
        # Pre-tenant routing lookup: runtime roles read it, only the owner writes.
        op.execute("GRANT SELECT ON channel_account TO csl_runtime, csl_worker")
        op.execute("REVOKE ALL ON channel_account FROM csl_provider, csl_analyst, csl_public")


def downgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    op.drop_index("ix_outbox_provider_message", table_name="outbox_message")
    with op.batch_alter_table("outbox_message") as b:
        b.drop_column("last_error")
        b.drop_column("priority")
        b.drop_column("message_json")
    with op.batch_alter_table("conversation") as b:
        b.drop_column("state_json")
    if pg:
        op.execute("REVOKE ALL ON channel_account FROM csl_runtime, csl_worker")
    op.drop_table("channel_account")
