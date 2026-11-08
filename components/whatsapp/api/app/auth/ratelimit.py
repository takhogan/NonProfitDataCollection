"""In-process rate limits (API-111).

A fixed-window counter keyed by (bucket, client key). It is per process: with
N instances the effective limit is N times higher, so production should run a
single instance or move counters to a shared store (Postgres or Redis) behind
the same `RateLimiter.hit` interface.
"""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from fastapi import Request

from app.config import get_settings
from app.errors import RateLimited


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def hit(self, bucket: str, key: str, limit: int, window_s: float = 60.0) -> float | None:
        """Count one request. Return None if allowed, else seconds until reset."""
        if limit <= 0:
            return None
        now = self._clock()
        with self._lock:
            start, count = self._windows.get((bucket, key), (now, 0))
            if now - start >= window_s:
                start, count = now, 0
            count += 1
            self._windows[(bucket, key)] = (start, count)
            if len(self._windows) > 50_000:  # bound memory under a flood
                cutoff = now - window_s
                self._windows = {k: v for k, v in self._windows.items() if v[0] >= cutoff}
            if count > limit:
                return max(0.0, window_s - (now - start))
        return None

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    hops = get_settings().forwarded_for_trusted_hops
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


def _enforce(bucket: str, limit: int, request: Request) -> None:
    retry = limiter.hit(bucket, client_ip(request), limit)
    if retry is not None:
        raise RateLimited(
            "rate limit exceeded",
            details={"bucket": bucket},
            headers={"Retry-After": str(max(1, math.ceil(retry)))},
        )


def limit_signin(request: Request) -> None:
    """Dependency: per-IP limit on every sign-in step."""
    _enforce("signin", get_settings().rate_limit_signin_per_minute, request)


def limit_webhook(request: Request) -> None:
    """Dependency: per-IP limit on provider webhooks."""
    _enforce("webhook", get_settings().rate_limit_webhook_per_minute, request)
