# WhatsApp adapter

Provider boundary for the WhatsApp Business Platform, with a fake local adapter.
Choose direct Meta integration or a provider during implementation after verifying
current setup requirements and documentation. No live integration exists yet.

## Responsibilities

- Verify inbound requests using provider-documented mechanisms.
- Normalize messages and status events while preserving provider/account identifiers.
- Submit supported reply/template messages and normalize send errors.
- Expose message-window and template metadata needed by outbound orchestration.
- Provide fake inbound events, outbound capture, duplicate events, and failure fixtures.

Intake questions and case creation belong in contracts/domain/operational-worker, not this adapter.
The application must check permission and permitted message type before sending;
the adapter should reject unsupported operations. Provide clear handoff and opt-out
paths in the conversation flow.

Store credentials outside Git. Redact phone numbers and message content from routine
logs. Raw payload storage, if needed, is restricted and time-limited. Document provider
retry behavior and delivery guarantees before relying on them.

First deliverable: a fake adapter capable of completing the Spanish intake locally
without contacting real people.

## Tech stack and deployment

The stack was decided on 7 November 2026: Python, inside the backend package.

- HTTPX is used for provider HTTP calls, and `hmac`/`hashlib` for signature checks
  (`hmac.compare_digest`).
- Pydantic models carry the normalized events.
- The adapter interface is a `typing.Protocol`.
- Tests use pytest with an HTTPX mock transport for provider fixtures and for
  retry/error scenarios.

This is a module used by the API (webhooks) and the operational worker (sends), not an
independent server. Today the webhook verification and inbound persistence live in
`whatsapp/api/app/routers/webhooks.py`. As the adapter grows, move the provider-specific
parts behind the `WA-001` interface.

The live implementation is a direct Meta Cloud API adapter built by a separate
contributor against this repo's interface and conformance suite (see
[REQUIREMENTS.md](REQUIREMENTS.md)). Keep a provider-neutral interface so a
business solution provider can be substituted without changing case logic. Pin the
provider API version and verify its current documentation during implementation.

## Planned interface and modules

Expose `verifyWebhook`, `normalizeInbound`, `sendReply`, `sendTemplate`, and
`normalizeDeliveryUpdate`. Keep `src/provider`, `src/normalization`, `src/signatures`,
`src/errors`, and `src/fake` separate. Return provider message IDs and categorized
errors; never turn provider payloads directly into domain mutations.

The API must preserve the original request bytes for verification before parsing
JSON. Treat account IDs as configured mappings to organizations. A claimed tenant
field in a provider message is not trusted. Separate webhook setup verification from
validation of incoming event authenticity.

## Delivery behavior and first implementation

Implement text and structured choices first; defer audio/media ingestion until
retention, processing, and access requirements are defined. Treat delivery callbacks
as asynchronous events that may repeat or arrive out of order. A provider acceptance
response is not recipient receipt or confirmation of aid delivery.

The fake adapter captures outbound messages and simulates success, rate limits,
timeouts, duplicate callbacks, and ambiguous sends. Follow with a live adapter in a
controlled test account. Verify account mapping, signature rejection, timeout handling,
redacted logs, message-window enforcement, and opt-out suppression before pilot use.
