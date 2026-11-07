# Shared contracts

Versioned boundary formats with runtime validation and derived TypeScript types.

Own API inputs/responses, domain command inputs, internal events, normalized
messages, questionnaire versions, and stable status/category definitions.
Do not expose database rows wholesale as API responses.

Conventions:

- UUID identifiers, UTC timestamp serialization, explicit local timezone metadata.
- Explicit units and requested periods; liters and device sessions are incompatible.
- Unknown values remain unknown, rather than silently becoming zero or false.
- Distinguish service status, evidence review status, need status, sharing state, and outcome facts.
- Include schema/event versions and idempotency identifiers where applicable.
- Provide structured error codes for validation, capacity, conflict, and authorization.
- Public/read-model DTOs exclude sensitive fields unless the use case authorizes them.

First deliverable: household assisted-intake payload, assessment confirmation,
case detail response, need definitions, and the partner list row.

## Python boundary

Add versioned JSON Schemas and shared fixtures for external data jobs and results.
Derive and validate TypeScript and Python models against that format. See the
[data-job protocol](data-jobs.md); the queue implementation is not the contract.

## Proposed tech stack and source of truth

Use checked-in JSON Schema Draft 7 as the source of truth for wire formats. Validate
in TypeScript with Ajv and in Python with `jsonschema.Draft7Validator`; explicitly
configure format checking in both runtimes. Generate TypeScript types with
`json-schema-to-typescript` during the build. Python may use typed wrappers internally,
but the checked-in schema remains authoritative at the boundary.

Choose a deliberately portable schema subset: explicit objects, enums, required
fields, numeric bounds, and versioned references. Do not depend on coercion, injected
defaults, or runtime-specific regular expressions. Bundle references locally; schema
validation must not fetch arbitrary remote documents. Use OpenAPI 3.0 descriptions
for staff endpoints, with an explicit conversion/compatibility check for any schema
features outside its supported subset.

## Planned layout

`schemas/common`, `schemas/api/v1`, `schemas/events/v1`, `schemas/data-jobs/v1`,
`fixtures/valid`, `fixtures/invalid`, and `generated/typescript`. Distribute the same
schema files with the Python image; no dynamic network schema downloads are needed.
Questionnaire versions are data linked to stable answer schemas, not executable code.

## Evolution and verification

Version persisted events as well as endpoints. Keep consumers compatible with queued
older versions during rollout; reject unsupported versions explicitly and route
failed events for review. Required-field additions or meaning changes need a new
version. CI regenerates types and checks drift, then runs identical payload fixtures
through both validators. Test unknown versus absent values, units, timestamps,
additional fields, and nested errors. Validate service-specific semantics in domain
logic after structural validation.

References: [Fastify schema validation](https://fastify.dev/docs/latest/Reference/Validation-and-Serialization/),
[Python jsonschema](https://python-jsonschema.readthedocs.io/en/stable/).
