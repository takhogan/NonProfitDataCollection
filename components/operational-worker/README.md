# Operational worker

Process durable jobs independently from HTTP requests while sharing domain rules.

## Proposed stack and hosting

Proposal dated 7 November 2026; not provisioned or implemented.

- **Language/runtime:** TypeScript compiled to JavaScript, running on a supported
  Node.js LTS release. Pin compatible runtime and dependency versions when building.
- **Queue library:** `pg-boss`, backed by PostgreSQL in a dedicated queue schema.
  Use the existing managed database initially, with bounded connection pools.
- **Application logic:** import `domain`, `database`, `contracts`, and `whatsapp`
  workspace packages. Use the same domain commands as the API.
- **Packaging:** a Docker image built from the repository root so shared packages
  are available. Run compiled JavaScript as a long-lived process.
- **Production host:** one continuously running Render Background Worker service
  initially, alongside a Render API web service and managed Render Postgres/PostGIS.
  The worker needs outbound network access but no public HTTP endpoint.
- **Region:** propose Virginia, USA, with API, worker, and database colocated for
  private networking. Confirm the NGO's hosting/data-location requirements before
  provisioning; this is not a claim that data must or may legally be hosted there.
- **Local development:** Docker Compose for PostgreSQL/PostGIS, with API and worker
  running locally through workspace scripts; use the fake WhatsApp adapter.

This choice reuses the existing TypeScript code and PostgreSQL operations. Queue
traffic shares database capacity with application queries, so monitor contention
and connection usage. Budget for continuous worker compute and managed database
capacity; this proposal does not assume free hosting or a nonprofit discount.

Render documents [continuously running background workers](https://render.com/docs/background-workers),
[Docker deployments](https://render.com/docs/docker),
[PostGIS support](https://render.com/docs/postgresql-extensions), and
[same-region private networking](https://render.com/docs/regions).
[pg-boss](https://github.com/timgit/pg-boss) provides a Node.js/PostgreSQL queue.
These capabilities were checked for this proposal; cost and deployment sizing are
still to be established.

## Responsibilities

- Normalize accepted inbound messages and advance resumable conversation state.
- Serialize conversation updates so concurrent messages do not corrupt intake.
- Submit outbound messages from the transactional outbox.
- Apply provider delivery updates without regressing status on older events.
- Retry transient failures with bounded backoff and expose terminal failures for staff.
- Later: reminders, lightweight report comparison rules, retention, and operational exports.
- Accept validated external evidence through domain commands and create review tasks.
  External data retrieval and geospatial processing belong to `data-worker`.

Use pg-boss for scheduling and execution, with application-owned durable inbox and
outbox records for accepted messages and outbound intents.
Use leases, attempt counts, operation IDs, and explicit organization context.
Do not claim exactly-once network delivery: handle uncertain send outcomes using
provider capabilities and reconciliation rather than blindly resending.

Keep core assistance decisions synchronous and transactional in domain commands.
Worker crashes must not lose accepted messages or duplicate needs or follow-ups.

## Job flow and consistency

1. The API authenticates a webhook and commits a deduplicated inbox record.
2. A dispatcher scans pending inbox records and submits jobs containing record IDs,
   organization ID, event version, and an operation key. Avoid raw personal data in jobs.
3. A handler loads the record within explicit organization context, serializes changes
   to its conversation, and commits domain changes, processing status, and any outbox
   intent in one transaction.
4. An outbox dispatcher submits send jobs; the send handler applies contact permission
   and messaging-window rules before calling the provider and recording the outcome.

Dispatch and enqueue may be retried after a crash. Use job deduplication plus durable
application operation keys; a duplicate job must be harmless even if queue-level
deduplication has expired. Pending-record scans recover lost scheduling attempts.
Handle ambiguous external send outcomes through reconciliation, not an assumption
that a queue guarantees exactly-once WhatsApp delivery.

Start with separate job types for inbound intake, outbound sending, and status
updates. The separate Python `data-worker` handles external data retrieval and
geospatial processing. It does not consume pg-boss jobs or import TypeScript domain
code. See the [cross-language job contract](../contracts/data-jobs.md).
An accepted data result creates a durable processing intent; this worker applies
domain commands to link evidence and enqueue human review, without automatically
denying aid or changing need or sharing decisions.

## Deployment and operations

- Add a worker Dockerfile and a root `render.yaml` during implementation, with
  separate API/worker start commands. They are planned files, not existing setup.
- Test and build before deployment. Run database and queue-schema migrations once
  in a controlled release step, with backward-compatible changes during rollouts.
  Do not let every worker replica independently run privileged migrations.
- Keep credentials in the host's secret configuration. Use separate migration and
  runtime database roles, and restrict queue access to trusted backend processes.
  Queue metadata may span organizations; domain reads/writes must still enforce
  organization isolation and must not run with a tenant-bypass role.
- Start with one worker instance and bounded handler concurrency. Serialize by
  conversation across replicas, not just within one process. Scale after measuring
  backlog, job duration, database pressure, and provider rate limits.
- On shutdown, stop claiming jobs, finish in-flight work within a configured grace
  period, and release resources. Interrupted work must be safe to retry after expiry.
- Configure job timeouts, bounded retries/backoff, and a failed-job review path.
  Distinguish permanent invalid requests from transient provider/network failures.
- Emit redacted structured logs and monitor heartbeat age, oldest pending job,
  queue depth, processing time, retry/failure rates, and pending outbox age. A live
  process is insufficient evidence that it is processing jobs successfully.
- Treat local disk as disposable; durable jobs and conversation state live in
  PostgreSQL. Store any retained media in restricted object storage when required.

Acceptance checks: restart during intake; retry after committing but before queue
acknowledgement; deliver duplicate events; interrupt an outbound send; and exhaust
retries. Confirm no lost accepted report, duplicate need or follow-up, unpermitted send,
cross-organization access, or silent permanent failure.

First deliverable: consume a synthetic inbox event and produce a durable outbound
intent, including restart/retry verification.

## Detailed stack and internal modules

Use TypeScript, Node.js LTS, pg-boss, the shared `pg` persistence package, Pino JSON
logging, and Vitest. Build with the pnpm workspace and `tsc`; ship a production Docker
image with compiled code and runtime dependencies. There is no separate HTTP framework
inside the worker. Choose compatible pinned versions as part of the first build.

Planned modules: `src/bootstrap` (config/start/stop), `src/dispatchers` (inbox/outbox),
`src/handlers` (typed jobs), `src/conversations` (intake orchestration), and
`src/telemetry` (heartbeat and counters). Business mutations still use `domain`.

## Initial job catalog

- `intake.process`: inbox ID → conversation transition and confirmed assessment intent.
- `message.send`: outbox ID → provider submission record or classified failure.
- `message.status`: event ID → monotonic provider-status update.
- `evidence.ingest`: accepted data-result ID → idempotent evidence links/review task.
- `followup.due`: case/permission references → a permitted message intent or staff task.

Job payloads contain IDs, organization context, operation key, and schema version;
handlers reload current permissions and state before acting. Do not embed complete
household profiles or mutable state snapshots in jobs. Each handler defines timeout,
retry classification, deduplication behavior, and what staff see on terminal failure.

Start with intake and outbound delivery, then status events, then evidence ingestion.
Use separate concurrency budgets to keep provider slowness from exhausting database
connections. Record a stable job/operation correlation ID across API, queue, and
provider calls. Keep operational backlog visible to staff even if the worker stops.
