# Data processing worker

Python component for ingesting external sources and producing geographically and
temporally scoped evidence. This is a component plan, not a runnable implementation.

## Stack and deployment

- Python on a supported release, with pinned dependencies and a separate lockfile.
- Candidate processing libraries: pandas, GeoPandas, Rasterio, and Xarray. Select
  only those needed by the first validated data source; verify runtime and native
  dependency compatibility during implementation.
- Separate Docker image, including any required geospatial native dependencies.
- Proposed host: a separate Render Background Worker, initially one instance,
  colocated with the API. Provision when the first external-source pipeline is ready.
- Local execution: Python environment or its Docker image, fixture datasets, and
  the local API. No live source credentials are required for initial development.
- Store durable output in restricted object storage; treat local scratch space as
  disposable and enforce memory, download-size, and scratch-space limits.

## Responsibilities

1. Retrieve permitted external datasets for an approved area, service, and time range.
2. Normalize coordinates, observation times, source versions, and quality metadata.
3. Calculate source-specific indicators or anomalies against an explicit baseline.
4. Produce evidence candidates with provenance, spatial/temporal scope, quality
   limitations, processing version, and output artifact references.
5. Return results through the authenticated internal API for validation and review.

Do not access household contacts, send WhatsApp messages, modify case/need states,
allocate aid, or make eligibility decisions. Process aggregate areas by default;
individual household coordinates must not be required for initial pipelines.
An absent or unusable measurement is unknown, not evidence that services are working.

## Job boundary

Use a language-neutral, versioned JSON contract over an internal authenticated API.
The API persists data jobs and results in application-owned PostgreSQL tables.
Python claims and acknowledges those jobs via API calls; it never reads the backend's
job tables and has no direct application database credentials.

See [data job lifecycle and result contract](../contracts/data-jobs.md) for leases,
retries, idempotency, organization scope, and artifact handling. The API owns durable
job state; the worker owns only the execution of its current leased attempt.

## Module layout to implement

- `sources`: approved-source adapters and provenance capture.
- `processing`: spatial/temporal normalization and source-specific calculations.
- `jobs`: claim/heartbeat/complete/fail client and bounded execution loop.
- `models`: validated request/result models derived from the shared schemas.
- `tests`: small synthetic or redistributable fixtures and contract tests.

Separate source acquisition from transformation so a pipeline can be replayed
against fixed fixtures. Preserve observation time separately from retrieval time.
Record license and permitted uses; do not embed arbitrary source credentials or
accept arbitrary download URLs supplied by job payloads.

## First deliverable and acceptance

Use one fixture-based pipeline to claim a job, compute an area-level indicator,
upload a synthetic result, and create a reviewable evidence candidate through the
API and operational worker. Source selection follows the separate research chat.

Verify expired leases, duplicate completion, lost completion responses, cancellation,
malformed output, wrong-organization access, unavailable source data, and oversized
inputs. None may produce duplicate evidence or automatic aid denial. Monitor oldest
pending job, heartbeat age, runtime, failures, resource usage, and source freshness.

## Detailed stack

- Python with `uv` for environment/dependency locking and `pyproject.toml` packaging.
- HTTPX for internal API calls and bounded streaming downloads from approved sources.
- Python `jsonschema` for the shared Draft 7 job/result contracts; typed internal
  models can use dataclasses without creating a competing wire-format definition.
- NumPy/pandas for numeric/tabular transforms; GeoPandas for vector geography;
  Rasterio for raster windows/masks; Xarray for labeled multidimensional data.
  These are planned options, installed per pipeline rather than all required at boot.
- Standard-library JSON logging, pytest for pipelines/contracts, and Ruff for lint/format.
- Docker for a repeatable native-library environment; no FastAPI, Celery, Redis,
  PostgreSQL driver, or job-queue client is required for the current pull-via-API design.

Pin Python and geospatial dependency versions together and verify the image can read
actual source formats. Add Dask or distributed processing only after measuring a
pipeline that exceeds bounded single-worker execution.

## Processing stages and resource isolation

The parent process claims work and maintains its lease. Execute CPU-heavy processing
in a supervised child process so lease renewal and cancellation stay responsive.
Stop/terminate the child after cancellation, lease loss, or the job deadline; a stale
attempt cannot publish an accepted result. Start with one processing child per instance.

Each pipeline implements discover → acquire → validate coverage/quality → normalize →
compute → write artifacts → submit result. Use windowed reads and clipped areas where
available, record CRS/resampling/baseline choices, and reject data outside the allowed
job scope. Distinguish source acquisition failure from a successful result with no
usable observations. Both need visibility but have different retry behavior.

A result must include measurement time, retrieval time, source/version, method/version,
spatial/temporal scope, units, quality flags, and limitations. Save a reproducible
manifest with checksums and permitted source references. Never label an anomaly as a
verified household outage or interpret unavailable measurements as normal service.

## Implementation sequence

First build the API client and fixture pipeline with no geospatial dependencies.
Next add one researched source with bounded historical retrieval and known fixtures.
Then add its specific native libraries and operational freshness checks. Finally
benchmark memory/runtime and set job budgets before enabling a recurring schedule.
The parent should continue heartbeats during slow downloads and transformations.

References: [uv](https://docs.astral.sh/uv/), [HTTPX](https://www.python-httpx.org/),
[Python jsonschema](https://python-jsonschema.readthedocs.io/en/stable/).
