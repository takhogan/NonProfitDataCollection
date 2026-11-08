"""Injected collaborators: clock, ID generation, and persistence protocols.

The domain never imports SQLAlchemy. The database session implements these
protocols with org-scoped queries (DB-002); tests use in-memory fakes. Invariants
that need locks or unique constraints (one open need per reporter key and category,
idempotency keys) must also be enforced by the database, not only here.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol

from app.domain.types import (
    Activity,
    AlertSubscription,
    IndicatorSnapshot,
    Permission,
    PrivacyProfile,
    ProviderOrganization,
    Report,
    ReporterCommState,
    ReviewTask,
    SentMessage,
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Test clock; ``advance`` moves it forward."""

    def __init__(self, at: datetime):
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, delta) -> None:
        self._at = self._at + delta


class IdGenerator(Protocol):
    def new_id(self, prefix: str) -> str: ...


class SequentialIds:
    def __init__(self) -> None:
        self._n = itertools.count(1)

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self._n)}"


class ProfileRepository(Protocol):
    def active(self, org_id: str) -> PrivacyProfile: ...
    def by_version(self, org_id: str, version: int) -> PrivacyProfile: ...
    def by_notice_version(self, org_id: str, notice_version: str) -> Optional[PrivacyProfile]: ...


class ReportRepository(Protocol):
    def get(self, org_id: str, report_id: str) -> Optional[Report]: ...
    def save(self, report: Report) -> None: ...
    def confirmed_in_window(
        self, org_id: str, start: datetime, end: datetime
    ) -> Iterable[Report]: ...
    def latest_for_reporter(self, org_id: str, reporter_key: str) -> Iterable[Report]: ...


class ProviderRepository(Protocol):
    def get(self, org_id: str, provider_id: str) -> Optional[ProviderOrganization]: ...
    def save(self, provider: ProviderOrganization) -> None: ...


class ActivityRepository(Protocol):
    def for_org(self, org_id: str) -> Iterable[Activity]: ...
    def save(self, activity: Activity) -> None: ...


class PermissionRepository(Protocol):
    def for_reporter(self, org_id: str, reporter_key: str) -> Iterable[Permission]: ...
    def save(self, permission: Permission) -> None: ...


class CommStateRepository(Protocol):
    def get(self, org_id: str, reporter_key: str) -> ReporterCommState: ...
    def sent_since(self, org_id: str, reporter_key: str, since: datetime) -> Iterable[SentMessage]: ...


class SubscriptionRepository(Protocol):
    def active_for_org(self, org_id: str) -> Iterable[AlertSubscription]: ...


class ReviewTaskRepository(Protocol):
    def get(self, org_id: str, task_id: str) -> Optional[ReviewTask]: ...
    def save(self, task: ReviewTask) -> None: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: IndicatorSnapshot) -> None: ...
    def latest(self, org_id: str, bucket) -> Optional[IndicatorSnapshot]: ...


class OutboxWriter(Protocol):
    """Audit events and outbound intents written in the same transaction (DOM-003)."""

    def audit(self, org_id: str, action: str, details: dict) -> None: ...
    def outbound(self, org_id: str, intent) -> None: ...
