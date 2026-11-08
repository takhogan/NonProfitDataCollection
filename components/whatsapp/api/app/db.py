"""Database engine, session factory, FastAPI session dependency, and the
tenant transaction helper (DB-002, DB-032, DB-034).

Tenant context
--------------
Every tenant read or write runs inside ``tenant_transaction``. It opens one
transaction, and on PostgreSQL sets *transaction-local* context before any
statement:

- ``SET LOCAL ROLE <group role>`` chosen from the actor's app role
  (``ROLE_TO_DB_ROLE``), so RLS applies even on an owner/superuser login
  (disable with ``DB_ROLE_SWITCH=0`` only if the login is already a
  non-owner runtime role)
- ``set_config('app.org_id' | 'app.actor_id' | 'app.role' |
  'app.provider_org_id' | 'app.request_id', value, true)``
- ``statement_timeout`` and ``idle_in_transaction_session_timeout``

Everything resets at COMMIT/ROLLBACK, so pooled connections never leak a
tenant. With no tenant set, RLS policies return no rows. ``app.actor_id`` is
the actor's **membership id**.

On SQLite (quick demos only) there is no RLS; the context is kept in
``session.info["tenant"]`` and isolation relies on application filters.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _make_engine(url: str):
    # check_same_thread is a SQLite-only argument; needed because TestClient
    # and the dev server may touch the connection from different threads.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite") and url not in ("sqlite://", "sqlite:///:memory:"):
        # Ensure the parent directory for a file-based SQLite DB exists.
        path = url.split("sqlite:///", 1)[-1]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session (no tenant context)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tenant transaction helper
# ---------------------------------------------------------------------------

# App role -> PostgreSQL group role created by migration 2a7c4e91d3b0.
ROLE_TO_DB_ROLE: dict[str, str] = {
    "org_admin": "csl_runtime",
    "coordinator": "csl_runtime",
    "reviewer": "csl_runtime",
    "intake_volunteer": "csl_runtime",
    "provider": "csl_provider",
    "analyst": "csl_analyst",
    "public": "csl_public",
    "system": "csl_worker",  # workers, jobs, seeds
}

STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "15000"))
IDLE_IN_TX_TIMEOUT_MS = int(os.environ.get("DB_IDLE_IN_TX_TIMEOUT_MS", "30000"))


def _role_switch_enabled() -> bool:
    return os.environ.get("DB_ROLE_SWITCH", "1").strip().lower() not in ("0", "false", "no")


class TenantContextError(RuntimeError):
    """Raised for an invalid tenant context or misuse of the helper."""


@dataclass(frozen=True)
class TenantContext:
    org_id: str | None
    actor_id: str | None  # membership id (or "worker:<name>" for system jobs)
    role: str
    provider_org_id: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLE_TO_DB_ROLE:
            raise TenantContextError(f"unknown role {self.role!r}")
        if self.role != "system" and not self.org_id:
            raise TenantContextError("org_id is required except for role 'system'")
        if self.role == "provider" and not self.provider_org_id:
            raise TenantContextError("provider sessions need provider_org_id")


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def apply_tenant_context(session: Session, ctx: TenantContext) -> None:
    """Set transaction-local tenant context on the session's current transaction.

    Call only inside an open transaction (``tenant_transaction`` does this).
    """
    session.info["tenant"] = ctx
    if not _is_postgres(session):
        return
    if _role_switch_enabled():
        # Role name comes from the fixed whitelist above, never from input.
        session.execute(text(f"SET LOCAL ROLE {ROLE_TO_DB_ROLE[ctx.role]}"))
    session.execute(
        text(
            "SELECT set_config('app.org_id', :org, true),"
            " set_config('app.actor_id', :actor, true),"
            " set_config('app.role', :role, true),"
            " set_config('app.provider_org_id', :po, true),"
            " set_config('app.request_id', :rid, true),"
            " set_config('statement_timeout', :st, true),"
            " set_config('idle_in_transaction_session_timeout', :it, true)"
        ),
        {
            "org": ctx.org_id or "",
            "actor": ctx.actor_id or "",
            "role": ctx.role,
            "po": ctx.provider_org_id or "",
            "rid": ctx.request_id or "",
            "st": str(STATEMENT_TIMEOUT_MS),
            "it": str(IDLE_IN_TX_TIMEOUT_MS),
        },
    )


@contextmanager
def tenant_transaction(
    org_id: str | None,
    actor_id: str | None,
    role: str,
    *,
    provider_org_id: str | None = None,
    request_id: str | None = None,
    session: Session | None = None,
    isolation_level: str | None = None,
) -> Iterator[Session]:
    """Run one transaction with tenant/actor context set transaction-locally.

    Commits on success, rolls back on error. Pass ``session`` to reuse a
    request session (it must not already be inside a transaction); otherwise a
    new session is opened and closed. ``isolation_level="REPEATABLE READ"`` is
    for consistent contact-list exports (DB-033). Never call the network
    (WhatsApp, email) inside the block (DB-032).
    """
    ctx = TenantContext(org_id, actor_id, role, provider_org_id, request_id)
    own = session is None
    s = session if session is not None else SessionLocal()
    if s.in_transaction():
        raise TenantContextError(
            "tenant_transaction needs a session with no open transaction; "
            "commit/rollback first"
        )
    try:
        with s.begin():
            if isolation_level and _is_postgres(s):
                s.connection(execution_options={"isolation_level": isolation_level})
            apply_tenant_context(s, ctx)
            yield s
    finally:
        s.info.pop("tenant", None)
        if own:
            s.close()


@contextmanager
def system_transaction(actor_id: str = "worker", *, session: Session | None = None
                       ) -> Iterator[Session]:
    """Tenant-less worker transaction (job claims, inbox routing).

    RLS-protected tenant tables return no rows here; job/inbox tables are
    readable. Open a ``tenant_transaction(org_id, ..., role="system")`` to act
    on a tenant's data.
    """
    with tenant_transaction(None, actor_id, "system", session=session) as s:
        yield s


def current_tenant(session: Session) -> TenantContext | None:
    return session.info.get("tenant")


# ---------------------------------------------------------------------------
# Pre-tenant lookups and job claims
# ---------------------------------------------------------------------------

def lookup_api_key(key_hash: str, *, session: Session | None = None) -> dict[str, Any] | None:
    """Resolve an API key by hash before the tenant is known.

    Uses the ``api_key_lookup`` RLS policy (``app.api_key_hash``). Returns
    org/membership/provider ids and scopes for a live (unrevoked, unexpired)
    key, or None. The caller then opens a ``tenant_transaction`` for that org.
    """
    own = session is None
    s = session if session is not None else SessionLocal()
    try:
        with s.begin():
            if _is_postgres(s):
                if _role_switch_enabled():
                    s.execute(text("SET LOCAL ROLE csl_runtime"))
                s.execute(text("SELECT set_config('app.api_key_hash', :h, true)"), {"h": key_hash})
            row = s.execute(
                text(
                    "SELECT id, organization_id, membership_id, provider_organization_id, scopes,"
                    " expires_at FROM api_key WHERE key_hash = :h AND revoked_at IS NULL"
                    " AND expires_at > CURRENT_TIMESTAMP"
                ),
                {"h": key_hash},
            ).mappings().first()
            return dict(row) if row else None
    finally:
        if own:
            s.close()


_CLAIM_SQL = """
UPDATE job SET status = 'running', attempts = attempts + 1, lease_owner = :worker,
       lease_expires_at = now() + make_interval(secs => :lease), updated_at = now()
 WHERE id IN (
   SELECT id FROM job
    WHERE ((status = 'queued' AND run_after <= now())
           OR (status = 'running' AND lease_expires_at < now()))
      AND attempts < max_attempts
      AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
    ORDER BY priority, run_after
    LIMIT :limit
    FOR UPDATE SKIP LOCKED)
RETURNING id, organization_id, kind, payload_json, attempts
"""


def claim_jobs(session: Session, worker_id: str, *, kinds: list[str] | None = None,
               limit: int = 10, lease_seconds: int = 60) -> list[dict[str, Any]]:
    """Claim up to ``limit`` due jobs with ``FOR UPDATE SKIP LOCKED`` (DB-034).

    Run inside ``system_transaction`` and commit promptly; do the work in a
    separate tenant transaction per job. Expired leases are reclaimed.
    PostgreSQL only.
    """
    if not _is_postgres(session):
        raise NotImplementedError("claim_jobs needs PostgreSQL (SKIP LOCKED)")
    rows = session.execute(
        text(_CLAIM_SQL),
        {"worker": worker_id, "lease": lease_seconds, "kinds": kinds, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]
