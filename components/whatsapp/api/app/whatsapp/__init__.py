"""WhatsApp provider adapter boundary.

Exposes a small protocol (WhatsAppAdapter) with two implementations:
- GraphApiAdapter: real Meta WhatsApp Business Platform Graph API (via httpx).
- FakeAdapter: in-memory capture for local dev and tests; contacts no network.

This package depends only on config/stdlib/httpx. It must not import case or
household persistence (see components/whatsapp/README.md dependency rules).
"""
from app.whatsapp.adapter import (  # noqa: F401
    FakeAdapter,
    GraphApiAdapter,
    SendError,
    SendResult,
    WhatsAppAdapter,
    get_adapter,
)
