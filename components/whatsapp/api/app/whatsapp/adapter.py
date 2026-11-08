"""WhatsApp send adapters: real Graph API and a fake for local/testing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import get_settings


@dataclass
class SendResult:
    provider_message_id: str


class SendError(Exception):
    """Raised when a send fails. `retryable` drives the sender loop's backoff."""

    def __init__(self, message: str, *, retryable: bool = True, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class WhatsAppAdapter(Protocol):
    def send_text(self, *, phone_number_id: str, to: str, body: str) -> SendResult:
        """Send a text message. Returns the provider message id or raises SendError."""
        ...


class GraphApiAdapter:
    """Meta WhatsApp Business Platform Graph API adapter.

    Auth: Bearer WHATSAPP_TOKEN. The sending number is identified by
    phone_number_id in the URL path. Only free-form text is supported here;
    template sends (outside the 24h window) are a later concern.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        timeout: float = 10.0,
    ):
        settings = get_settings()
        self._token = token if token is not None else settings.whatsapp_token
        self._base_url = (base_url or settings.whatsapp_api_base).rstrip("/")
        self._api_version = api_version or settings.whatsapp_api_version
        self._timeout = timeout

    def send_text(self, *, phone_number_id: str, to: str, body: str) -> SendResult:
        url = f"{self._base_url}/{self._api_version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:  # network/timeout: retryable
            raise SendError(f"network error sending WhatsApp message: {exc}", retryable=True)

        if resp.status_code >= 500:
            raise SendError(
                f"WhatsApp API {resp.status_code}: {resp.text[:300]}",
                retryable=True, status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            # 4xx: client error (bad token, bad recipient). Not worth blind retry.
            raise SendError(
                f"WhatsApp API {resp.status_code}: {resp.text[:300]}",
                retryable=False, status_code=resp.status_code,
            )

        data = resp.json()
        try:
            provider_message_id = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            raise SendError(f"unexpected WhatsApp API response: {data}", retryable=False)
        return SendResult(provider_message_id=provider_message_id)


@dataclass
class FakeAdapter:
    """In-memory adapter for local dev and tests. Never contacts the network.

    Captures sent messages in `sent`. Set `fail_times` to simulate N consecutive
    retryable failures before succeeding, or `fatal` to raise a non-retryable error.
    """

    sent: list[dict] = field(default_factory=list)
    fail_times: int = 0
    fatal: bool = False
    _counter: int = 0

    def send_text(self, *, phone_number_id: str, to: str, body: str) -> SendResult:
        if self.fatal:
            raise SendError("fake fatal error", retryable=False)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise SendError("fake transient error", retryable=True)
        self._counter += 1
        mid = f"wamid.FAKE{self._counter}"
        self.sent.append(
            {"phone_number_id": phone_number_id, "to": to, "body": body, "id": mid}
        )
        return SendResult(provider_message_id=mid)


# Process-wide adapter. Tests swap this via set_adapter(); the worker reads it.
_adapter: WhatsAppAdapter | None = None


def get_adapter() -> WhatsAppAdapter:
    """Return the active adapter.

    Uses the fake adapter when WHATSAPP_ADAPTER=fake (default outside production),
    otherwise the real Graph API adapter.
    """
    global _adapter
    if _adapter is None:
        settings = get_settings()
        if settings.whatsapp_adapter == "fake":
            _adapter = FakeAdapter()
        else:
            _adapter = GraphApiAdapter()
    return _adapter


def set_adapter(adapter: WhatsAppAdapter | None) -> None:
    """Override the active adapter (tests, or explicit wiring)."""
    global _adapter
    _adapter = adapter
