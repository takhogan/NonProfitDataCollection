"""Request-ID, access-log, cache and deprecation middleware (pure ASGI).

- Request ID: accept a well-formed client `X-Request-ID` (8-64 chars of
  [A-Za-z0-9._-]) or generate one; echo it on the response, expose it to
  handlers as `request.state.request_id` and to logs via a context var.
- Access log: one JSON line per request with the route *template*
  (`/v1/households/{household_id}`), never the raw path or query string.
- `Cache-Control: no-store` on every non-public response (SEC-07).
- Legacy unversioned routes (`/orgs/...`, `/me`, `/auth/login`) carry
  `Deprecation: true` and a `Link` to the `/v1` successor.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.logs import request_id_var

_RID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
access_log = logging.getLogger("app.access")



def _successor(path: str) -> str | None:
    if path.startswith("/orgs/"):
        # /orgs/{org}/households/... -> /v1/households/...
        parts = path.split("/", 3)
        return "/v1/" + parts[3] if len(parts) > 3 else "/v1/me"
    if path == "/me" or path.startswith("/me/"):
        return "/v1" + path
    if path == "/auth/login":
        return "/v1/auth/password/login"
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for k, v in scope.get("headers", []):
            if k == b"x-request-id":
                incoming = v.decode("latin-1")
                break
        rid = incoming if _RID_OK.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        token = request_id_var.set(rid)
        path: str = scope.get("path", "")
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = rid
                if not path.startswith("/public/") and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
                succ = _successor(path)
                if succ is not None:
                    headers["Deprecation"] = "true"
                    headers["Link"] = f'<{succ}>; rel="successor-version"'
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or "<unmatched>"
            state = scope.get("state", {})
            access_log.info(
                "request",
                extra={
                    "method": scope.get("method", ""),
                    "route": template,
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "user_id": state.get("user_id", ""),
                    "auth_method": state.get("auth_method", ""),
                    "request_id": rid,
                },
            )
            request_id_var.reset(token)
