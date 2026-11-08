# Shared contracts

Versioned boundary formats: Pydantic models in the Python backend, exported as OpenAPI
and JSON Schema for the web app and the data worker.

Own API inputs/responses, domain command inputs, internal events, normalized
messages, questionnaire versions, and stable status/category definitions.
Do not expose database rows wholesale as API responses.

Conventions:

- UUID identifiers, UTC timestamp serialization, explicit local timezone metadata.
- Explicit units and requested periods; liters, people, and devices are never mixed.
- Unknown values remain unknown, rather than silently becoming zero or false.
- Distinguish service status, evidence review status, need status, sharing state, and outcome facts.
- Include schema/event versions and idempotency identifiers where applicable.
- Provide structured error codes for validation, conflict, authorization, and profile violations.
- Public/read-model DTOs exclude sensitive fields unless the use case authorizes them.

First deliverable: the report submission (with profile-dependent location), need
definitions, the indicator cell, the coverage cell, and the activity model.

## Data worker boundary

The data worker is a separate Python project with its own lockfile. It does not import
the backend package. Data-job request and result models are defined in Pydantic in the
backend, exported as versioned JSON Schemas, checked in, and validated in the data
worker with `jsonschema`. See the [data-job protocol](data-jobs.md). The job-table
implementation is not the contract.

## Tech stack and source of truth

The stack was decided on 7 November 2026 (Python backend).

- **Source of truth:** Pydantic v2 models in the backend (currently
  `whatsapp/api/app/contracts`). Use strict models with `extra="forbid"` at external
  boundaries, explicit enums, and explicit `"unknown"` values. Do not rely on silent
  coercion.
- **OpenAPI:** FastAPI generates the OpenAPI document. CI exports it to
  `contracts/openapi.json` and fails if it differs from the checked-in copy.
- **Web types:** the web app generates TypeScript types from that file with
  `openapi-typescript`. Generated types are never hand-edited.
- **JSON Schema:** event and data-job models are exported with
  `model_json_schema()` into `contracts/schemas/`, versioned, and checked in.
- **Shared fixtures:** valid and invalid JSON fixtures are validated by the Pydantic
  models in the backend, and by `jsonschema` against the exported schema in the data
  worker. Both must agree.

Keep exported schemas to a portable subset: explicit objects, enums, required fields,
numeric bounds, and local references only. Schema validation must not fetch remote
documents.

## Planned layout

The models and exporter live in the backend package. Checked-in artifacts go under
`components/contracts/`:

- `openapi.json`
- `schemas/events/v1/`, `schemas/data-jobs/v1/`
- `fixtures/valid/`, `fixtures/invalid/`

The data worker image packages `schemas/` from the same repository revision. Questionnaire
versions are data linked to stable answer schemas, not executable code.

## Evolution and verification

Version persisted events as well as endpoints. Keep consumers compatible with queued
older versions during rollout; reject unsupported versions explicitly and route
failed events for review. Required-field additions or meaning changes need a new
version. CI re-exports OpenAPI and JSON Schemas, checks drift, regenerates web types, and
runs the shared fixtures through Pydantic and `jsonschema`. Test unknown versus absent values, units, timestamps,
additional fields, and nested errors. Validate service-specific semantics in domain
logic after structural validation.

References: [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/),
[openapi-typescript](https://openapi-ts.dev/),
[Python jsonschema](https://python-jsonschema.readthedocs.io/en/stable/).
