# Data worker requirements

The Python worker that turns external sources into area-level, provenance-rich evidence
candidates. It never touches households, contacts, or aid decisions. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md). Protocol: [data-jobs.md](../contracts/data-jobs.md).
Source research: [Venezuela aid corroboration sources](../../reports/Venezuela%20aid%20corroboration%20sources.md).

## Scope and boundaries

- **DAW-001 (P0) Area-level only.** Inputs are area geometries and time windows. Outputs
  are indicators per area and window. The worker never receives household data, contact
  data, or precise points (`API-103`).
- **DAW-002 (P0) No decisions.** Results are evidence candidates. The worker cannot
  change reports, needs, review dispositions, or evidence status. The API and the
  operational worker decide linking (`DOM-074`).
- **DAW-003 (P0) Approved sources only.** Sources are a code-level registry of source
  IDs, each with license, permitted uses, and attribution. Jobs reference source IDs;
  arbitrary URLs in payloads are rejected.
- **DAW-004 (P0) Unknown is not normal.** Missing, cloud-covered, or unusable data
  produces `data_availability = unavailable | partial`, with no value. It never
  produces "service available".

## Job execution

- **DAW-010 (P0) Claim loop.** The worker claims, heartbeats, and completes or fails
  jobs per the protocol. Its parent process keeps the lease while a child process does
  the work.
- **DAW-011 (P0) Fencing.**
  - On lease loss, cancellation, or deadline, the worker kills the child process and
    does not submit.
  - Completion responses that were lost are retried with the same payload, so they are
    idempotent.
- **DAW-012 (P0) Budgets.** Per-job limits on wall time, memory, download bytes, and
  scratch disk, configurable per source. When a budget is exceeded, the job fails as
  terminal with a redacted reason.
- **DAW-013 (P0) Failure classes.** The worker distinguishes:
  - source unavailable (retryable)
  - source returned no usable data (success with `unavailable`)
  - invalid job (terminal)
  - internal error (retryable, with a cap)

## Pipeline stages

- **DAW-020 (P0) Standard stages.** Every pipeline runs discover → acquire → validate
  coverage and quality → normalize → compute → write artifacts → submit, and each stage
  is logged with its timing.
- **DAW-021 (P0) Replayability.** Acquisition is separated from transformation. Each
  pipeline runs against checked-in fixtures in CI and produces byte-stable results for
  fixed inputs.
- **DAW-022 (P0) Provenance.** Each result records the fields required by the contract:
  - measurement time and retrieval time
  - source and version, and license reference
  - method version, and processing image revision
  - CRS and resampling choices
  - baseline used
  - quality flags and limitations

## Mock Monitor Ciudad source (P0)

The live Monitor Ciudad feed is not accessible (D10), so the pilot uses a mock source
that follows an assumed schema (`CON-023`). The mock should behave realistically
enough to exercise review and map features end to end.

- **DAW-030 (P0) Mock generator.** A deterministic, seedable generator produces
  `MonitorCiudadReport` records for the pilot parishes and sectors (D5), with:
  - pseudonymous informant IDs (a stable pool of about 300 informants)
  - diurnal reporting patterns
  - scripted outage scenarios: a parish-wide blackout, a sector-level water cut,
    intermittent service, and a restoration
  - a background of normal-service reports
- **DAW-031 (P0) Realistic data quality.** The mock includes:
  - late reports (observed time well before the submission time)
  - duplicate submissions
  - unknown or unresolvable sector aliases
  - informants who stop reporting
  - areas with no informants, so "unknown" coverage can be tested
- **DAW-032 (P0) Source adapter interface.** The `monitor_ciudad` source has adapters
  `mock` (P0) and `live` (P2, not implemented). Selection is by configuration, and
  downstream contracts are identical for both.
- **DAW-033 (P0) Indicator.** Each job produces a `monitor_ciudad_service_status`
  indicator per area, service, and window:
  - counts by status
  - distinct informants
  - latest observation time
  - share reporting unavailable
  - `data_availability`

  Informant IDs are dropped from the output, and only counts leave the worker.
- **DAW-034 (P0) Independence and limits.** Results record that informant reports are
  volunteer observations of their own locations, not a census. A low informant count
  (fewer than 3) sets a `low_coverage` quality flag. Results are labelled with source
  kind `external_monitor`, distinct from residents' reports.
- **DAW-035 (P0) Scenario control.** Developers and demo staging can trigger named
  scenarios ("apagón Libertador 2026-11-10 19:00–23:00") to rehearse surge, review, and
  map behavior.
- **DAW-036 (P2) Live adapter.** Implement once CSL/Monitor Ciudad provides the schema,
  access method, and sharing terms. Live data is mapped to the same indicator, and the
  mapping is validated against the mock's fixtures.

## Night lights in shadow mode (P1)

- **DAW-040 (P1) NOAA-20 Black Marble.**
  - Retrieve VJ146A1/A2 (NRT and standard) tiles covering the pilot parishes, using
    Earthdata authentication.
  - Compute a radiance anomaly against a per-area baseline (e.g., the same weekday
    nights, trailing 60 days, quality-filtered).
- **DAW-041 (P1) Quality handling.** Use only quality-controlled observed radiance, not
  gap-filled radiance. Report the valid pixel fraction, cloud share, and latest real
  observation. Below a valid-fraction threshold, the result is `unavailable`.
- **DAW-042 (P1) Shadow mode.**
  - Indicators are stored and shown only on the map's context layer for reviewers.
  - They create no review tasks until a calibration study against reviewed episodes
    shows usefulness.
  - Suomi-NPP is used only for history (distribution ended 2026-11-02).
- **DAW-043 (P2) Additional sources.** IODA/Cloudflare connectivity signals, CHIRPS v3
  rainfall, and Sentinel-2 reservoir extent, each only when tied to a concrete operating
  decision (see the research report).

## Artifacts and storage

- **DAW-060 (P0) Artifacts.**
  - Intermediate rasters and manifests are written to restricted object storage (D14)
    through job-scoped upload URLs, with checksums.
  - Mock-source runs produce only a JSON manifest.
- **DAW-061 (P0) Scratch hygiene.** Local scratch is deleted after each job. No source
  credentials or attempt tokens appear in logs or artifacts.

## Operations and quality

- **DAW-070 (P0) Configuration.** The worker runs with only a service credential,
  internal API URL, source credentials (P1), and budgets. It has no database credentials.
- **DAW-071 (P0) Telemetry.** JSON logs with job ID and stage, heartbeat age, runtime,
  bytes downloaded, peak memory, failures by class, and source freshness (age of the
  newest available source data).
- **DAW-072 (P0) Tests.** Contract fixtures shared with the backend (`CON-042`), plus pipeline
  fixtures:
  - an expired lease
  - a duplicate completion
  - a lost completion response
  - cancellation
  - malformed output
  - a wrong-organization area
  - an unavailable source
  - an oversized input

  None may create duplicate evidence.
- **DAW-073 (P0) Deployment.** A separate Docker image runs one instance colocated with
  the API. It is deployed only when the mock pipeline passes end to end with the API
  and operational worker.
