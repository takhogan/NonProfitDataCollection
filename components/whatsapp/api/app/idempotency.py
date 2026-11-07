"""Idempotency-Key support for retryable mutations.

If the client sends an `Idempotency-Key` header, the first successful response
for (org, endpoint, key) is stored. A retry with the same key replays the stored
response instead of re-running the mutation, so an offline retry cannot create
duplicate households/cases.

Usage:
    with idempotent(request, response, ctx, db, endpoint="create_intake") as r:
        if r.hit:
            return Model.model_validate(r.body)
        result = do_work()
        r.store(201, result.model_dump())
        return result

No key header => the block runs normally and nothing is stored.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.context import RequestContext
from app.errors import Conflict
from app.models.system import IdempotencyKey

HEADER = "Idempotency-Key"


@dataclass
class Replay:
    hit: bool = False
    status: int = 0
    body: Any = None
    _key: str | None = None
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
            response_body=body,
        )
        self._db.add(row)
        try:
            self._db.commit()
        except IntegrityError:
            # A concurrent request stored the same key first; replay that one.
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
) -> Iterator[Replay]:
    key = request.headers.get(HEADER)
    replay = Replay(_key=key, _ctx=ctx, _db=db, _endpoint=endpoint, _response=response)

    if key:
        existing = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.organization_id == ctx.org_id,
                IdempotencyKey.endpoint == endpoint,
                IdempotencyKey.key == key,
            )
        )
        if existing is not None:
            replay.hit = True
            replay.status = existing.response_status
            replay.body = existing.response_body
            response.headers[HEADER] = key

    yield replay
