# Cross-language data jobs

Proposed interface between the Python backend (API and operational worker) and the
separate Python data worker. No endpoints or machine-readable schemas have been implemented yet.

## Ownership and transport

- The backend defines job request and result models in Pydantic and exports them as
  versioned JSON Schemas under `components/contracts/schemas/data-jobs/`. The data
  worker validates against those files with `jsonschema`. Neither side's internal
  types alone is the wire format.
- The API owns an application `data_job` table and validated `data_job_result`
  records, separate from the operational worker's job tables.
- Python uses authenticated internal HTTP endpoints. Authenticate worker identity,
  restrict allowed job types and organizations, and derive scope from that identity
  and the persisted job. Never trust an organization ID in the payload alone.
- Completion commits the result, job status, and an operational processing intent
  atomically. A retryable dispatcher schedules evidence ingestion as an operational worker job;
  domain-level operation keys prevent duplicate evidence or review tasks.

## Lifecycle and planned endpoints

1. Authorized staff or a scheduler creates a job through an API command. Persist
   an idempotency key unique within the organization and job type.
2. `POST /internal/data-jobs/claim` atomically leases one eligible job. Return a
   unique attempt token and lease expiry. Concurrent workers cannot claim the same
   active attempt. Increment the attempt counter on each claim.
3. `POST /internal/data-jobs/{id}/heartbeat` renews only a current, unexpired lease.
4. `POST /internal/data-jobs/{id}/complete` accepts schema-valid results only from
   the authorized holder of the current, unexpired lease. Fence out stale attempts.
5. `POST /internal/data-jobs/{id}/fail` records a redacted error and classifies it
   as retryable or terminal. Bounded retries use backoff and a next-attempt time.

States: pending → running → succeeded, with retry_wait, failed, and cancelled
branches. A sweeper reschedules expired attempts up to a maximum attempt count.
Cancellation invalidates active attempts; subsequent completions are rejected.
An identical retry of an already accepted completion returns the saved result;
a different payload for that completion key is a conflict. A lost response is not
permission to create a second result.

Persist at least: job ID, organization, job type, schema version, input, status,
idempotency key, attempt count, next-attempt time, lease-token hash, lease expiry,
processing version, result reference, and redacted failure reason. Audit manual retries.

## Request fields

```text
schema_version, job_id, organization_id, job_type, operation_key
source_id, source_version?, area_id, area_geometry_reference
service_type, observation_window_start, observation_window_end
baseline_window?, parameters, processing_version
attempt_token, lease_expires_at
```

Use approved source IDs rather than arbitrary URLs. Resolve geometry and authorized
artifact references through scoped API access. All instants use UTC; include CRS
and geometry version in the area definition. Bound area, time range, and input size.
Attempt credentials must never enter logs or output artifacts.

## Result fields

```text
schema_version, job_id, operation_key, processing_version
source_id, source_version?, source_reference, license_reference
observed_from, observed_to, retrieved_at
area_id, geometry_version, spatial_resolution?, temporal_resolution?
indicator_type, value?, unit?, baseline_reference?, method_version
quality_flags, limitations, data_availability
artifact_references[], artifact_checksums[]
```

`data_availability` distinguishes usable, partial, and unavailable observations.
An unavailable result may have no indicator value; absence must not become zero.
Indicators describe source measurements, not a person's truthfulness. The API
validates allowed types/units, times, provenance, finite values, size limits, and
organization ownership of artifacts. Operational domain logic decides which
observations may be linked and whether to open a human review task.

For large outputs, issue short-lived, job-scoped upload authorization to restricted
object storage. Verify uploaded objects and checksums before accepting completion;
reject unrelated object references and clean up abandoned attempt artifacts after
the configured retention period. Keep raw datasets out of queue payloads.

## Verification

Use shared valid/invalid JSON fixtures in both runtimes. Exercise concurrent claim,
heartbeat expiry, stale completion, duplicate completion, cancellation, retry limits,
tenant mismatch, unavailable data, and atomic result-to-operational-intent recording.
