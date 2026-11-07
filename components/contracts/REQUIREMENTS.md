# Contracts requirements

Versioned wire formats shared by web, API, workers, and Python. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Conventions

- **CON-001 (P0) Source of truth.**
  - JSON Schema Draft 7 files are checked in.
  - TypeScript types are generated, and a drift check runs in CI.
  - Python validates with `jsonschema` against the same files.
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
  - Response DTOs exclude contact addresses, names, landmarks, and points unless a
    `*Sensitive` variant is requested and authorized.
  - Masked forms are separate fields (`contact_masked`).
- **CON-005 (P0) Portable subset.** No coercion, no injected defaults, no remote
  `$ref`, and no runtime-specific regex features.

## API payloads (v1)

- **CON-010 (P0) Intake.**
  - `AssessmentSubmission`: channel, relationship, area/landmark, observations[],
    needs[], questionnaire version, operation key.
  - `AssessmentDraft`: the same fields, all optional, for bot drafts.
- **CON-011 (P0) Need details.**
  - Need categories: `water_drinking`, `water_other`, `charging`.
  - `WaterNeedDetail` (shared by both water categories), and `ChargingNeedDetail`
    with `ChargingDeviceRequest[]`.
  - The category determines the required detail.
- **CON-012 (P0) Case views.** `CaseSummary` (queue row) and `CaseDetail` (needs,
  timeline, observations, sharing history, outcome facts, review flags).
- **CON-013 (P0) Sharing.**
  - `PartnerOrganization`: vetting, scope, responsible contact, flags.
  - `NeedSharingUpdate`: shareable on/off, with a reason.
  - `ShareEvent`.
  - `ExportRequest` and `ExportRecord`: scope, format, row count, watermark ID,
    expiry.
- **CON-014 (P0) Partner contactable row.** `PartnerListRow` contains only the D17
  fields:
  - reference code, sector, landmark
  - category, quantity or people, urgency, preferred window
  - access notes
  - phone

  It has no history, notes, or review data. The schema rejects extra properties.
- **CON-018 (P1) Outcomes and directory.**
  - `PartnerOutcomeReport` (outcome, optional quantity, operation key).
  - `ResidentOutcomeReply`.
  - `ServicePoint` (for the directory).
- **CON-015 (P0) Review.** `ReviewTask`, `ObservationLink`, `ReviewDisposition`.
- **CON-016 (P0) Read models.**
  - `AreaConditionCell`: area, service, bucket, counts by status, distinct
    households, freshness, unknown share, suppressed flag.
  - `NeedDemandCell`: area × category, with counts of open needs, households, and
    people (when known), and urgency mix. Small cells are suppressed.
  - `BacklogSummary`, kept separate by category.
- **CON-017 (P0) Admin.** `Membership` (roles, partner organization), `CampaignConfig`
  (with display identity), and `PolicyVersion`.

## Events and jobs

- **CON-020 (P0) Normalized messaging events.** `InboundMessage` (text, interactive
  reply, location, media placeholder) and `DeliveryStatusEvent`. These are
  provider-neutral, and the provider IDs are preserved.
- **CON-021 (P0) Internal events.** `IntakeProcessJob`, `MessageSendJob`,
  `MessageStatusJob`, `EvidenceIngestJob`, `FollowupDueJob`. Each carries only IDs,
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
  stable `AssessmentSubmission`, and original answers are preserved.

## Errors and versioning

- **CON-040 (P0) Error envelope.** Errors have the form `{code, message_key, details,
  request_id}`. Codes:
  - `validation_failed`
  - `not_found`
  - `forbidden`
  - `conflict`
  - `stale_version`
  - `capacity_exceeded`
  - `invalid_transition`
  - `idempotency_conflict`
  - `rate_limited`
  - `unsupported_version`
- **CON-041 (P0) Versioning.**
  - Endpoints, events, and data jobs carry versions.
  - Adding a required field, or changing a field's meaning, means a new version.
  - Consumers accept the previous version during rollouts.
- **CON-042 (P0) Shared fixtures.** Valid/invalid fixtures run through Ajv and Python
  `jsonschema` in CI. They cover unknown vs absent, units, timestamps, extra fields,
  and nested errors.
- **CON-043 (P0) OpenAPI.** OpenAPI 3.0 docs for staff endpoints are generated from the
  schemas, with a compatibility check.
