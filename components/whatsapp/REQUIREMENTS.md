# WhatsApp adapter requirements

Provider boundary for the WhatsApp Business Platform, plus the fake adapter used
everywhere except production. Conversation logic lives in the
[operational worker](../operational-worker/REQUIREMENTS.md). Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Ownership (D7, D18)

- **A separate contributor** builds and operates:
  - the production **Meta Cloud API** adapter
  - the Meta Business account and the bot number
  - display-name approval for "Metron Reporter"
  - message templates
  - provider secrets
- **This repo** owns:
  - the adapter interface (`WA-001`)
  - the normalized contracts (`CON-020`)
  - the template registry format (`WA-032`)
  - the fake adapter (`WA-050`–`052`)

  It also owns the conformance test suite that the production adapter must pass.
- In the requirements below, **[contributor]** marks requirements on the production
  adapter; this repo only verifies them. **[repo]** marks work done here.
- **WA-002a (P0) [repo] Conformance suite.** A shared test suite runs against any
  adapter implementation: the fake adapter in CI, and the Meta adapter in a test
  account. It covers WA-010–013, WA-030–033, and WA-061. The production adapter is
  accepted only when the suite passes.
- **WA-002b (P0, D18) Integration agreement.** A short written agreement settles who
  hosts the webhook (`API-100`), where secrets live, who registers and approves each
  template in `OPW-033`, how interface changes are versioned, and the joint incident
  contact.

## Interface

- **WA-001 (P0) [repo] Provider-neutral interface.** The adapter exposes:
  - `verifyWebhook(rawBody, headers)`
  - `verifySetupChallenge(query)`
  - `normalizeInbound(payload)`
  - `normalizeStatus(payload)`
  - `sendReply(...)`, `sendInteractive(...)`, `sendTemplate(...)`
  - `lookupMessage(providerMessageId)`, where the provider supports it
  - `capabilities()`

  A business solution provider (BSP) can replace Meta Cloud API without changing worker
  code (D7).
- **WA-002 (P0) Account mapping.** A channel account (phone number ID) maps to an
  organization and campaign set by configuration. Tenant claims in payloads are ignored.
- **WA-003 (P0) Error categories.** Send errors are normalized to:
  - `rate_limited` (retryable, with retry-after)
  - `transient`
  - `outside_window`
  - `template_not_approved`
  - `recipient_unavailable`
  - `invalid_request`
  - `auth`
  - `unknown_outcome`

## Inbound

- **WA-010 (P0) [contributor] Signature verification.** Verify the `X-Hub-Signature-256` HMAC over the
  raw request bytes, with a constant-time compare. The setup challenge is handled
  separately.
- **WA-011 (P0) [contributor] Normalization.** Text, interactive replies (button/list IDs), location,
  and media placeholders are normalized to `InboundMessage`. Each keeps the provider
  message ID, sender endpoint, provider timestamp, and context (reply-to) ID.
- **WA-012 (P0) Batch payloads.** One webhook payload may contain several messages and
  statuses. Each is normalized and deduplicated individually.
- **WA-013 (P0) Unsupported types.** Stickers, reactions, contacts, and unknown types
  are normalized as `unsupported`, so the worker can reply helpfully instead of failing.

## Media

- **WA-020 (P0/P1) Voice notes and images.**
  - P0: emit a media placeholder (type, size, and provider media ID) without
    downloading the media.
  - P1 (D13): download on demand into restricted object storage, with checksum and
    retention date. Provider media URLs are never stored or shown to staff directly.

## Outbound

- **WA-030 (P0) [contributor] Messages.**
  - Plain text replies.
  - Interactive buttons (≤ 3) and lists (≤ 10 rows), with length limits validated
    before sending.
  - Approved templates with named parameters.
  - Each send returns the provider message ID or a categorized error.
- **WA-031 (P0) Window metadata.** The adapter exposes the information needed to decide
  between a free-form reply and a template, given the last inbound time. Enforcement
  belongs to the outbound gate (`DOM-061`).
- **WA-032 (P0) Template registry.** Templates (name, language `es`, category, parameter
  schema, approval status) are kept in configuration. Sending an unregistered or
  unapproved template fails locally without calling the provider.
- **WA-033 (P0) [contributor] Timeouts.** Sends have a bounded timeout. A timeout after the request
  was written returns `unknown_outcome`, not a failure, so the worker can reconcile it
  (OPW-032).

## Identity and branding

- **WA-040 (P0) Display identity.** The bot's business display name, profile, and
  about text follow D2/SEC-12. A per-campaign greeting identity is configuration-driven.
  Registering the bot phone number and assigning Meta Business ownership must be decided
  before launch (D7).
- **WA-041 (P0) Entry links.** Generate `wa.me` links with prefilled text that contains
  only the opaque campaign token (e.g., `Hola #c-8f2k`). The token never contains
  names, numbers, or areas.

## Fake adapter

- **WA-050 (P0) [repo] Fake provider.**
  - An in-process and HTTP fake that accepts sends, records them for inspection, and
    emits status callbacks.
  - Synthetic residents can drive the full Spanish intake from a CLI or test.
- **WA-051 (P0) Fault injection.** The fake can be configured for:
  - duplicate webhooks
  - out-of-order status events
  - delayed delivery
  - rate limits
  - timeouts with unknown outcome
  - invalid signatures
  - outside-window rejections
  - batch payloads
- **WA-052 (P0) Dev chat console.** A local-only page (behind the dev flag) to chat
  with the bot as a synthetic resident. This supports Spanish copy review with CSL
  before any live number exists.

## Security and logging

- **WA-060 (P0) Secrets.** The app secret, access token, and verify token live in the
  host secret store, with rotation documented. Staging and production use separate
  apps and numbers.
- **WA-061 (P0) Redaction.** Logs show a masked endpoint and message IDs only, never
  message bodies or full numbers. Raw payload retention follows NFR-09.
- **WA-062 (P0) Pre-launch checks.** Before the live number goes live, verify:
  - signature rejection
  - account mapping
  - window enforcement
  - template sends
  - opt-out suppression
  - a duplicate-callback test with real webhook retries in a test account
