# Shared contracts

Versioned boundary formats with runtime validation and derived TypeScript types.

Own API inputs/responses, domain command inputs, internal events, normalized
messages, questionnaire versions, and stable status/category definitions.
Do not expose database rows wholesale as API responses.

Conventions:

- UUID identifiers, UTC timestamp serialization, explicit local timezone metadata.
- Explicit units and requested periods; liters and device sessions are incompatible.
- Unknown values remain unknown, rather than silently becoming zero or false.
- Distinguish service status, evidence review status, need status, and fulfillment status.
- Include schema/event versions and idempotency identifiers where applicable.
- Provide structured error codes for validation, capacity, conflict, and authorization.
- Public/read-model DTOs exclude sensitive fields unless the use case authorizes them.

First deliverable: household assisted-intake payload, assessment confirmation,
case detail response, and water/charging need definitions.
