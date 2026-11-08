# Contracts requirements

Versioned wire formats shared by the web app, the Python backend, providers' API clients, and the data worker. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Conventions

- **CON-001 (P0) Source of truth.**
  - Pydantic v2 models in the Python backend are authoritative.
  - The OpenAPI document and the event and data-job JSON Schemas are exported,
    checked in, and drift-checked in CI.
  - The web app generates TypeScript types from the OpenAPI document.
  - The data worker validates with `jsonschema` against the exported schemas.
- **CON-002 (P0) Common types.** Shared definitions for:
  - UUID
  - UTC instant
  - local timezone
  - time precision (`exact`, `approximate`, `day`, `unknown`)
  - quantity `{value, unit}` with units `liters`, `people`, and `devices`
  - area reference
  - pagination cursor
  - operation key
- **CON-003 (P0) Unknown vs absent.**
  - Tri-state fields use explicit `"unknown"`, not null or omission.
  - Omission means "not asked".
  - Schemas reject `0` or `false` as a stand-in for unknown where a tri-state is
    defined.
- **CON-004 (P0) No sensitive leakage by default.**
  - Aggregate, provider, public, and alert models have no personal fields.
  - Sensitive fields appear only in dedicated staff detail and contact-list models,
    after authorization and profile filtering (`API-004`).
  - Masked forms are separate fields (`contact_masked`).
- **CON-005 (P0) Strict, portable models.**
  - Boundary models use strict mode and `extra="forbid"`.
  - No silent coercion, no injected defaults on external input, no remote `$ref`, and
    no runtime-specific regex features in exported schemas.

## API payloads (v1)

- **CON-010 (P0) Reports.**
  - `ReportSubmission`: channel, relationship, area, `LocationDetail`, observations[],
    needs[], permissions[], questionnaire version, operation key.
  - `ReportDraft`: all fields optional.
  - `LocationDetail` is a discriminated union: `meeting_point` (meeting point ID or
    `none_nearby`) or `address` (encrypted-at-rest text and an optional point). The API
    rejects a variant that the org's profile disallows.
- **CON-011 (P0) Needs.**
  - Categories: `water_drinking`, `water_other`, `charging`.
  - `NeedDetail` fields: people affected, quantity `{value, unit}`, remaining supply,
    stated urgency, access notes, preferred times.
  - Lifecycle states follow `DOM-021`.
- **CON-012 (P0) Indicator cells.** `IndicatorCell` contains:
  - area, level, category or service, bucket
  - active needs; distinct reporters; distinct households (nullable by profile)
  - people affected known, and unknown count
  - urgency mix, supply mix, status mix
  - freshness
  - coverage label `none`/`thin`/`reported`
  - confidence label with reasons
  - suppressed flag
  - method version and input watermark
- **CON-013 (P0) Ranking and coverage.**
  - `AreaOfNeed`: a cell plus rank and the criteria used.
  - `CoverageCell`: area × category, `covered`/`uncovered`/`unknown`, plus activity
    references.
- **CON-014 (P0) Providers.**
  - `ProviderOrganization`, `Activity` (type, category, areas, schedule, capacity,
    public location, visibility, status, last confirmed), `AlertSubscription`, `Alert`
    (aggregate fields only), and `ApiKey` (metadata only).
  - The secret appears only once, in `ApiKeyCreated`.
- **CON-015 (P0) Contact list row.** `ContactListRow` is a discriminated union by profile:
  - `protective`: alias, sector, meeting point, category, urgency, preferred times,
    phone
  - `standard`: name, address, category, urgency, preferred times, phone

  `extra="forbid"`.
- **CON-016 (P0) Public models.** `PublicIndicatorCell` (banded counts, status mix,
  coverage, freshness) and `PublicActivity`. These are separate models and never
  subclasses of internal ones, so that new internal fields cannot leak.
- **CON-017 (P0) Review and admin.**
  - `ReviewTask`, `ReviewDisposition`.
  - `PrivacyProfile`, with each setting and its platform minimum.
  - `PolicyVersion`, `Membership`, `CampaignConfig`, `MeetingPoint`, `Broadcast`
    (template, activity, recipient count).

## Events and jobs

- **CON-020 (P0) Normalized messaging events.** `InboundMessage` (text, interactive
  reply, location, media placeholder) and `DeliveryStatusEvent`. These are
  provider-neutral, and the provider IDs are preserved.
- **CON-021 (P0) Internal jobs.** `IntakeProcessJob`, `MessageSendJob`,
  `MessageStatusJob`, `EvidenceIngestJob`, `IndicatorRefreshJob`, `AlertEvaluateJob`,
  `RefreshPromptJob`, `BroadcastJob`, `RetentionJob`. Each carries only IDs,
  organization, operation key, and schema version.
- **CON-022 (P0) Data jobs.** `DataJobRequest` and `DataJobResult` per
  [data-jobs.md](data-jobs.md), with `indicator_type` values for:
  - `monitor_ciudad_service_status` (P0)
  - `ntl_radiance_anomaly` (P1)
  - `rainfall_anomaly` (P2)
- **CON-023 (P0) Mock Monitor Ciudad record.** Schema of `MonitorCiudadReport`, the
  assumed upstream record used by the mock source:
  - pseudonymous informant ID
  - area code or alias
  - service
  - status
  - observed at, with precision
  - hours without service (optional)
  - submitted at

  It is marked `x-assumed: true` until D10 is resolved.

## Questionnaires

- **CON-030 (P0) Questionnaire definition.**
  - A questionnaire definition is data: steps, question types (choice, text, number,
    area, time-ago), branching conditions, Spanish text, allowed "No sé", and the
    answer-to-field mapping.
  - It is validated against a schema and never executed as code.
- **CON-031 (P0) Answer schema stability.** Each questionnaire version maps answers to a
  stable `ReportSubmission`, and original answers are preserved.

## Errors and versioning

- **CON-040 (P0) Error envelope.** Errors have the form `{code, message_key, details,
  request_id}`. Codes:
  - `validation_failed`
  - `not_found`
  - `forbidden`
  - `conflict`
  - `stale_version`
  - `invalid_transition`
  - `idempotency_conflict`
  - `rate_limited`
  - `unsupported_version`
  - `profile_violation` (a field the privacy profile disallows)
- **CON-041 (P0) Versioning.**
  - Endpoints, events, and data jobs carry versions.
  - Adding a required field, or changing a field's meaning, means a new version.
  - Consumers accept the previous version during rollouts.
- **CON-042 (P0) Shared fixtures.** Valid/invalid fixtures run through the backend's
  Pydantic models, and through `jsonschema` against the exported schemas, in CI. Both
  must agree. They cover unknown vs absent, units, timestamps, extra fields,
  and nested errors.
- **CON-043 (P0) OpenAPI.** FastAPI's generated OpenAPI is exported to
  `components/contracts/openapi.json`. CI fails if it is stale, or if the regenerated
  web types differ from the committed ones.
