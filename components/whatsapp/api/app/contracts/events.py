"""Normalized messaging events (CON-020; WA-011–WA-013, WA-020, WA-003).

Provider-neutral: the Meta adapter and the fake adapter both produce these. The
provider's own message IDs are kept. Tenant is resolved from ``channel_account_id``
by configuration (WA-002), never from the payload. Exported to
``schemas/events/v1/``. These events contain the sender endpoint and message text,
so they are restricted data: never log them unredacted (WA-061).
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .base import ContractModel, PhoneE164, UtcInstant, Uuid, not_asked

EVENT_SCHEMA_VERSION = "1"

MessagingProvider = Literal["meta_cloud", "fake"]
ProviderId = Annotated[str, StringConstraints(min_length=1, max_length=256, pattern="^[A-Za-z0-9._:=+/-]+$")]


class TextContent(ContractModel):
    type: Literal["text"]
    body: Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class InteractiveReplyContent(ContractModel):
    """A button or list reply. ``reply_id`` is the ID we set when sending."""

    type: Literal["interactive_reply"]
    reply_kind: Literal["button", "list"]
    reply_id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    title: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class LocationContent(ContractModel):
    """A shared location. The intake flow uses it only where the profile allows GPS."""

    type: Literal["location"]
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=256)] = not_asked()
    address: Annotated[str, StringConstraints(min_length=1, max_length=512)] = not_asked()


class MediaPlaceholderContent(ContractModel):
    """Media is not downloaded at P0 (WA-020). Provider media URLs are never stored."""

    type: Literal["media"]
    media_type: Literal["audio", "image", "video", "document"]
    mime_type: Annotated[str, StringConstraints(pattern="^[a-z]+/[A-Za-z0-9.+-]+(; ?[a-z]+=[A-Za-z0-9-]+)?$", max_length=128)]
    size_bytes: Annotated[int, Field(ge=0)] = not_asked()
    provider_media_id: ProviderId


class UnsupportedContent(ContractModel):
    """Stickers, reactions, contacts, unknown types (WA-013)."""

    type: Literal["unsupported"]
    provider_type: Annotated[str, StringConstraints(pattern="^[a-z0-9_]{1,64}$")]


InboundContent = Annotated[
    Union[
        TextContent,
        InteractiveReplyContent,
        LocationContent,
        MediaPlaceholderContent,
        UnsupportedContent,
    ],
    Field(discriminator="type"),
]


class InboundMessage(ContractModel):
    schema_version: Literal["1"]
    event_id: Uuid
    provider: MessagingProvider
    channel_account_id: ProviderId
    provider_message_id: ProviderId
    sender: PhoneE164
    provider_timestamp: UtcInstant
    received_at: UtcInstant
    context_message_id: ProviderId = not_asked(description="The message this one replies to.")
    content: InboundContent


SendErrorCategory = Literal[
    "rate_limited",
    "transient",
    "outside_window",
    "template_not_approved",
    "recipient_unavailable",
    "invalid_request",
    "auth",
    "unknown_outcome",
]


class DeliveryError(ContractModel):
    category: SendErrorCategory
    provider_code: Annotated[str, StringConstraints(pattern="^[A-Za-z0-9_.-]{1,64}$")] = not_asked()


class DeliveryStatusEvent(ContractModel):
    model_config = ConfigDict(
        json_schema_extra={
            "if": {"properties": {"status": {"const": "failed"}}},
            "then": {"required": ["error"]},
            "else": {"not": {"required": ["error"]}},
        }
    )

    schema_version: Literal["1"]
    event_id: Uuid
    provider: MessagingProvider
    channel_account_id: ProviderId
    provider_message_id: ProviderId
    recipient: PhoneE164
    status: Literal["sent", "delivered", "read", "failed"]
    provider_timestamp: UtcInstant
    received_at: UtcInstant
    error: DeliveryError = not_asked(description="Present exactly when status is 'failed'.")

    @model_validator(mode="after")
    def _error_iff_failed(self) -> "DeliveryStatusEvent":
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("error is present exactly when status is 'failed'")
        return self
