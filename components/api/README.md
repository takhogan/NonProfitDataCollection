# Application API

Own the authenticated HTTP boundary and compose domain commands with persistence.

## Endpoint groups

- Current user, authorized organization memberships, and staff assignments.
- Households, contacts, assessments, observations, cases, and needs.
- Water supplies, allocations, delivery runs/stops, and delivery recording.
- Charging sites, slots, reservations, and session recording.
- Reviews, dashboard read models, permissions, and later referrals.
- WhatsApp inbound message and delivery-status webhooks.

Validate request bodies with shared runtime contracts. Derive organization access
from authenticated membership, not a trusted request field. Pass explicit tenant and
actor context into transactions, and authorize both reads and mutations.

Accept idempotency keys for fulfillment and other retryable mutations. Return
structured validation, permission, conflict, and capacity errors. Authenticate
provider webhooks using the adapter; persist accepted events before acknowledging.
Do not perform long-running intake or network sends inside the webhook request.

First deliverable: authorized assisted-intake creation and household/case retrieval.
