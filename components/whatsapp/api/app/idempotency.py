"""Idempotency-Key support for retryable mutations (DOM-002).

If the client sends an `Idempotency-Key` header, the first successful response
for (org, endpoint, key) is stored together with a SHA-256 digest of the
validated request body and the acting user. A retry with the same key:
- same actor and same body  -> replays the stored response (no new work);
- different body or actor   -> 409 `idempotency_conflict`, nothing runs.

Usage:
    with idempotent(request, response, ctx, db, endpoint="create_intake",
                    payload=body.model_dump(mode="json")) as r:
        if r.hit:
            return Model.model_validate(r.body)
        result = do_work()
        r.store(201, result.model_dump(mode="json"))
        return result

No key header => the block runs normally and nothing is stored.

Storage note: until the database branch adds `request_digest` and `actor_id`
columns to `idempotency_key`, both live inside `response_body` as
`{"_v": 2, "request_digest", "actor_id", "body"}`. Rows written before this
change (a bare body) still replay, with no digest check.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.errors import IdempotencyConflict, ValidationError
from app.models.system import IdempotencyKey

HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 255


def request_digest(endpoint: str, payload: Any) -> str:
    canonical = json.dumps(
        {"endpoint": endpoint, "payload": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _unwrap(stored: Any) -> tuple[str | None, str | None, Any]:
    if isinstance(stored, dict) and stored.get("_v") == 2:
        return stored.get("request_digest"), stored.get("actor_id"), stored.get("body")
    return None, None, stored  # legacy row


@dataclass
class Replay:
    hit: bool = False
    status: int = 0
    body: Any = None
    _key: str | None = None
    _digest: str = ""
    _ctx: RequestContext | None = None
    _db: Session | None = None
    _endpoint: str = ""
    _response: Response | None = None

    def store(self, status: int, body: dict) -> None:
        if self._key is None:
            return  # no idempotency key supplied; nothing to persist
        row = IdempotencyKey(
            organization_id=self._ctx.org_id,
            endpoint=self._endpoint,
            key=self._key,
            response_status=status,
            response_body={
                "_v": 2,
                "request_digest": self._digest,
                "actor_id": self._ctx.actor_id,
                "body": body,
            },
        )
        self._db.add(row)
        try:
            self._db.commit()
        except IntegrityError:
            # A concurrent request stored the same key first; it wins.
            self._db.rollback()
        if self._response is not None:
            self._response.headers[HEADER] = self._key


@contextmanager
def idempotent(
    request: Request,
    response: Response,
    ctx: RequestContext,
    db: Session,
    *,
    endpoint: str,
    payload: Any = None,
) -> Iterator[Replay]:
    key = request.headers.get(HEADER)
    if key is not None and not (0 < len(key) <= MAX_KEY_LENGTH):
        raise ValidationError("bad idempotency key", details={"header": HEADER})
    digest = request_digest(endpoint, payload)
    replay = Replay(_key=key, _digest=digest, _ctx=ctx, _db=db, _endpoint=endpoint,
                    _response=response)

    if key:
        existing = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.organization_id == ctx.org_id,
                IdempotencyKey.endpoint == endpoint,
                IdempotencyKey.key == key,
            )
        )
        if existing is not None:
            stored_digest, stored_actor, body = _unwrap(existing.response_body)
            if stored_digest is not None and (
                not hmac.compare_digest(stored_digest, digest)
                or (stored_actor and stored_actor != ctx.actor_id)
            ):
                raise IdempotencyConflict(
                    "idempotency key reused with different input",
                    details={"header": HEADER},
                )
            replay.hit = True
            replay.status = existing.response_status
            replay.body = body
            response.headers[HEADER] = key

    yield replay
