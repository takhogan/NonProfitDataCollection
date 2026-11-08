"""WhatsApp send adapters: real Graph API and a fake for local/testing.

Messages are plain dicts built by ``app.whatsapp.catalog``:

- ``{"kind": "text", "body": ...}``
- ``{"kind": "buttons", "body": ..., "buttons": [{"id", "title"}, ...]}`` (max 3)
- ``{"kind": "list", "body": ..., "button": ..., "rows": [{"id", "title", "description"?}]}``
  (max 10 rows)
- ``{"kind": "template", "name": ..., "language": ..., "params": [...]}``

Errors carry two flags so the sender never double-sends (OPW-032):

- ``retryable``: the request certainly did not reach Meta (connect error, 5xx,
  429), so sending again is safe.
- ``uncertain``: the request may have been accepted (timeout after the body was
  written). The sender must NOT resend; it waits for a status webhook that
  carries our ``biz_opaque_callback_data`` and otherwise marks the row failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import get_settings

# WhatsApp interactive limits.
MAX_BUTTONS, BUTTON_TITLE = 3, 20
MAX_ROWS, ROW_TITLE, ROW_DESC, LIST_BUTTON = 10, 24, 72, 20
BODY_MAX = 1024


@dataclass
class SendResult:
    provider_message_id: str


class SendError(Exception):
    """Raised when a send fails."""

    def __init__(self, message: str, *, retryable: bool = True, uncertain: bool = False,
                 status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable and not uncertain
        self.uncertain = uncertain
        self.status_code = status_code


class WhatsAppAdapter(Protocol):
    def send(self, *, phone_number_id: str, to: str, message: dict,
             callback_data: str | None = None) -> SendResult: ...


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def graph_payload(to: str, message: dict, callback_data: str | None = None) -> dict:
    """Build the Graph API /messages body for a catalog message."""
    base: dict = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
    if callback_data:
        base["biz_opaque_callback_data"] = callback_data[:512]
    kind = message.get("kind", "text")
    body = _cut(message.get("body", ""), BODY_MAX)
    if kind == "text":
        return {**base, "type": "text", "text": {"preview_url": False, "body": body}}
    if kind == "buttons":
        buttons = [
            {"type": "reply", "reply": {"id": b["id"], "title": _cut(b["title"], BUTTON_TITLE)}}
            for b in message["buttons"][:MAX_BUTTONS]
        ]
        return {**base, "type": "interactive",
                "interactive": {"type": "button", "body": {"text": body},
                                "action": {"buttons": buttons}}}
    if kind == "list":
        rows = []
        for r in message["rows"][:MAX_ROWS]:
            row = {"id": r["id"], "title": _cut(r["title"], ROW_TITLE)}
            if r.get("description"):
                row["description"] = _cut(r["description"], ROW_DESC)
            rows.append(row)
        return {**base, "type": "interactive",
                "interactive": {"type": "list", "body": {"text": body},
                                "action": {"button": _cut(message.get("button", "Elegir"),
                                                          LIST_BUTTON),
                                           "sections": [{"title": "Opciones", "rows": rows}]}}}
    if kind == "template":
        tpl: dict = {"name": message["name"], "language": {"code": message.get("language", "es")}}
        params = message.get("params") or []
        if params:
            tpl["components"] = [{"type": "body", "parameters": [
                {"type": "text", "text": str(p)} for p in params]}]
        return {**base, "type": "template", "template": tpl}
    raise SendError(f"unknown message kind {kind!r}", retryable=False)


class GraphApiAdapter:
    """Meta WhatsApp Business Platform Graph API adapter (Bearer WHATSAPP_TOKEN)."""

    def __init__(self, token: str | None = None, base_url: str | None = None,
                 api_version: str | None = None, timeout: float = 10.0):
        settings = get_settings()
        self._token = token if token is not None else settings.whatsapp_token
        self._base_url = (base_url or settings.whatsapp_api_base).rstrip("/")
        self._api_version = api_version or settings.whatsapp_api_version
        self._timeout = timeout

    def send(self, *, phone_number_id: str, to: str, message: dict,
             callback_data: str | None = None) -> SendResult:
        url = f"{self._base_url}/{self._api_version}/{phone_number_id}/messages"
        payload = graph_payload(to, message, callback_data)
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Never left this machine: safe to retry.
            raise SendError(f"connect error: {type(exc).__name__}", retryable=True)
        except httpx.HTTPError as exc:
            # Read/write timeout or a dropped connection after submission.
            raise SendError(f"uncertain send: {type(exc).__name__}", uncertain=True)

        if resp.status_code >= 500 or resp.status_code == 429:
            raise SendError(f"WhatsApp API {resp.status_code}", retryable=True,
                            status_code=resp.status_code)
        if resp.status_code >= 400:
            code = ""
            try:
                err = resp.json().get("error", {})
                code = f" code={err.get('code')} {str(err.get('message', ''))[:120]}"
            except ValueError:
                pass
            raise SendError(f"WhatsApp API {resp.status_code}{code}", retryable=False,
                            status_code=resp.status_code)
        try:
            return SendResult(provider_message_id=resp.json()["messages"][0]["id"])
        except (KeyError, IndexError, TypeError, ValueError):
            # Accepted (2xx) but unreadable: treat as uncertain, never resend.
            raise SendError("unexpected WhatsApp API response", uncertain=True)

    # Step-1 compatibility (app.whatsapp.messaging).
    def send_text(self, *, phone_number_id: str, to: str, body: str) -> SendResult:
        return self.send(phone_number_id=phone_number_id, to=to,
                         message={"kind": "text", "body": body})


@dataclass
class FakeAdapter:
    """In-memory adapter for local dev and tests. Never contacts the network.

    Captures sent messages in ``sent``. ``fail_times`` raises N retryable errors
    first, ``fatal`` a permanent one, ``uncertain_times`` N uncertain ones.
    """

    sent: list[dict] = field(default_factory=list)
    fail_times: int = 0
    fatal: bool = False
    uncertain_times: int = 0
    _counter: int = 0

    def send(self, *, phone_number_id: str, to: str, message: dict,
             callback_data: str | None = None) -> SendResult:
        graph_payload(to, message, callback_data)  # same validation as the real adapter
        if self.fatal:
            raise SendError("fake fatal error", retryable=False)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise SendError("fake transient error", retryable=True)
        if self.uncertain_times > 0:
            self.uncertain_times -= 1
            raise SendError("fake uncertain error", uncertain=True)
        self._counter += 1
        mid = f"wamid.FAKE{self._counter}"
        self.sent.append({"phone_number_id": phone_number_id, "to": to, "message": message,
                          "body": message.get("body"), "id": mid,
                          "callback_data": callback_data})
        return SendResult(provider_message_id=mid)

    def send_text(self, *, phone_number_id: str, to: str, body: str) -> SendResult:
        return self.send(phone_number_id=phone_number_id, to=to,
                         message={"kind": "text", "body": body})


# Process-wide adapter. Tests swap this via set_adapter(); the worker reads it.
_adapter: WhatsAppAdapter | None = None


def get_adapter() -> WhatsAppAdapter:
    """Fake adapter when WHATSAPP_ADAPTER=fake (default outside production), else Graph."""
    global _adapter
    if _adapter is None:
        _adapter = FakeAdapter() if get_settings().whatsapp_adapter == "fake" else GraphApiAdapter()
    return _adapter


def set_adapter(adapter: WhatsAppAdapter | None) -> None:
    global _adapter
    _adapter = adapter
