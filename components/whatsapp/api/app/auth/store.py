"""Auth state repository: sessions, password credentials, TOTP, OIDC flows.

The API depends only on the `AuthStore` protocol. `InMemoryAuthStore` backs
tests and local development. After the database branch adds the tables listed
in the API report (`staff_session`, `staff_password_credential`,
`staff_totp_secret`, `oidc_login_flow`), a `SqlAuthStore` implements the same
protocol and `get_auth_store` returns it.

Session tokens are never stored: the store is keyed by SHA-256 of the token,
so a leaked database row cannot be replayed as a cookie.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Protocol


@dataclass
class StaffSession:
    id: str                    # random public id (for listing/revoking), not the token
    token_hash: str            # sha256(cookie token)
    user_id: str
    stage: str                 # "active" | "totp_enroll" | "totp_verify"
    auth_method: str           # "oidc_google" | "password_totp"
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime       # absolute limit
    active_org_id: str | None = None
    revoked_at: datetime | None = None


@dataclass
class PasswordCredential:
    user_id: str
    password_hash: str         # Argon2id encoded hash
    failed_count: int = 0
    locked_until: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class TotpSecret:
    user_id: str
    secret: str                # base32; encrypt at rest in the SQL store
    confirmed_at: datetime | None = None
    last_used_step: int = -1   # rejects replay of an accepted code


@dataclass
class OidcFlow:
    state: str
    nonce: str
    code_verifier: str
    browser_binding_hash: str  # sha256 of the flow cookie value
    next_path: str
    expires_at: datetime


class AuthStore(Protocol):
    # sessions
    def add_session(self, s: StaffSession) -> None: ...
    def get_session_by_token_hash(self, token_hash: str) -> StaffSession | None: ...
    def update_session(self, s: StaffSession) -> None: ...
    def delete_session(self, session_id: str) -> None: ...
    def revoke_user_sessions(self, user_id: str, at: datetime) -> int: ...
    def list_user_sessions(self, user_id: str) -> list[StaffSession]: ...
    # password
    def get_password(self, user_id: str) -> PasswordCredential | None: ...
    def put_password(self, c: PasswordCredential) -> None: ...
    # totp
    def get_totp(self, user_id: str) -> TotpSecret | None: ...
    def put_totp(self, t: TotpSecret) -> None: ...
    def delete_totp(self, user_id: str) -> None: ...
    # oidc
    def put_oidc_flow(self, f: OidcFlow) -> None: ...
    def pop_oidc_flow(self, state: str) -> OidcFlow | None: ...


@dataclass
class InMemoryAuthStore:
    _sessions: dict[str, StaffSession] = field(default_factory=dict)  # by token_hash
    _passwords: dict[str, PasswordCredential] = field(default_factory=dict)
    _totp: dict[str, TotpSecret] = field(default_factory=dict)
    _flows: dict[str, OidcFlow] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # Copies are returned so callers cannot mutate store state by accident;
    # writes go through update_*/put_* just like a SQL implementation.
    def add_session(self, s: StaffSession) -> None:
        with self._lock:
            self._sessions[s.token_hash] = replace(s)

    def get_session_by_token_hash(self, token_hash: str) -> StaffSession | None:
        with self._lock:
            s = self._sessions.get(token_hash)
            return replace(s) if s else None

    def update_session(self, s: StaffSession) -> None:
        with self._lock:
            if s.token_hash in self._sessions:
                self._sessions[s.token_hash] = replace(s)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            for h, s in list(self._sessions.items()):
                if s.id == session_id:
                    del self._sessions[h]

    def revoke_user_sessions(self, user_id: str, at: datetime) -> int:
        with self._lock:
            hashes = [h for h, s in self._sessions.items() if s.user_id == user_id]
            for h in hashes:
                del self._sessions[h]
            return len(hashes)

    def list_user_sessions(self, user_id: str) -> list[StaffSession]:
        with self._lock:
            return [replace(s) for s in self._sessions.values() if s.user_id == user_id]

    def get_password(self, user_id: str) -> PasswordCredential | None:
        with self._lock:
            c = self._passwords.get(user_id)
            return replace(c) if c else None

    def put_password(self, c: PasswordCredential) -> None:
        with self._lock:
            self._passwords[c.user_id] = replace(c)

    def get_totp(self, user_id: str) -> TotpSecret | None:
        with self._lock:
            t = self._totp.get(user_id)
            return replace(t) if t else None

    def put_totp(self, t: TotpSecret) -> None:
        with self._lock:
            self._totp[t.user_id] = replace(t)

    def delete_totp(self, user_id: str) -> None:
        with self._lock:
            self._totp.pop(user_id, None)

    def put_oidc_flow(self, f: OidcFlow) -> None:
        with self._lock:
            self._flows[f.state] = replace(f)

    def pop_oidc_flow(self, state: str) -> OidcFlow | None:
        with self._lock:
            return self._flows.pop(state, None)


_store: AuthStore = InMemoryAuthStore()


def get_auth_store() -> AuthStore:
    """FastAPI dependency. Tests override it; SQL wiring replaces the default."""
    return _store
