# Operational worker requirements

Asynchronous processing: the WhatsApp intake conversation, outbound messaging, status
updates, evidence ingestion, comparison rules, follow-ups, and retention. Shared context:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Processing guarantees

- **OPW-001 (P0) No lost accepted input.**
  - Every accepted inbox item is processed to a terminal state: processed, ignored with
    a reason, or failed and visible to staff.
  - A dispatcher scan recovers items whose job was lost.
- **OPW-002 (P0) Idempotent handlers.** Handlers use domain operation keys, so duplicate
  jobs, retries after commit, and replays create no duplicate assessments, needs,
  messages, or evidence.
- **OPW-003 (P0) Per-conversation ordering.**
  - Messages in one conversation are processed in received order, serialized across
    replicas (an advisory lock or singleton key per conversation).
  - Out-of-order provider delivery is reordered by provider timestamp within a short
    window (default 5 s).
- **OPW-004 (P0) Retry classification.**
  - Transient failures retry with exponential backoff (max 8 attempts or 1 hour).
  - Permanent failures go straight to a failed state with a redacted reason.
  - Failed items appear in a staff-visible list with replay (`API-064`).
- **OPW-005 (P0) Tenant context.** Each handler sets the org context from the persisted
  record, never from job payload alone, and runs under the RLS-bound worker role.

## WhatsApp intake conversation

The conversation engine lives in this repo. The production Meta adapter is built by a
separate contributor against the `WA-001` interface. All tests here run against the
fake adapter.

The conversation engine runs the questionnaire definition (`CON-030`) as a state
machine. Spanish copy follows the draft in [PLATFORM_PLAN.md](../../PLATFORM_PLAN.md).

- **OPW-010 (P0) Entry.**
  - The first message (with or without a campaign token) starts or resumes a
    conversation.
  - The campaign token sets attribution only; it is never treated as identity.
  - An unknown or expired token falls back to the default campaign.
- **OPW-011 (P0) Notice and permission.**
  - The bot introduces itself as **Metron Reporter** (OPW-020), names CSL as the
    organization responsible for the data, and explains:
    - what is collected and who sees it
    - that Metron Reporter does **not** deliver aid itself
    - that a report does not guarantee help

    It also offers a human.
  - It records the notice acknowledgement and messaging permission as separate records
    before any personal questions.
  - Declining ends the flow politely and keeps no personal data.
- **OPW-011a (P0) Sharing consent.** After needs are collected, and before the summary,
  the bot asks separately whether the resident agrees to share their contact and need
  with organizations that can help in their area. "No" is fully respected:
  - the need is still recorded
  - the bot explains that it will not appear on partner lists
  - the bot explains that CSL staff may follow up directly
- **OPW-011b (P0) Expectations.** The confirmation message says, in plain Spanish, that:
  - the request is recorded
  - with consent, it may be shared with organizations that may help
  - CSL does not control whether or when they respond
  - the resident will receive updates and can write `ESTADO` at any time
- **OPW-012 (P0) Structured questions.**
  - Questions use WhatsApp interactive buttons/lists where possible (max 3 buttons /
    10 list rows), with numbered text fallback.
  - Every question accepts "No sé".
  - Free text at a choice step is re-asked once, then accepted as a note and flagged
    for review.
- **OPW-013 (P0) Area resolution.**
  - The area is resolved from the parish/sector list, with alias matching on typed
    text. Ambiguous matches offer up to 3 candidates.
  - An unresolvable area is stored as text with `precision=unresolved` and creates a
    location review task.
  - A shared WhatsApp location is optional, coarsened to the area, and the precise
    point is handled per SEC-03.
- **OPW-014 (P0) Pause and resume.**
  - A conversation resumes at the last unanswered step for up to 48 hours. After that,
    the resident can start over or keep the previous answers.
  - "Menú" and "Atrás" commands are available at any step.
- **OPW-015 (P0) Summary and confirm.**
  - Shows a short Spanish summary. The resident can confirm, fix a field, or cancel.
  - Only confirmation creates needs (DOM-011).
  - The reply includes the reference code and the expected response time for staffed
    hours.
- **OPW-016 (P0) Global commands.** Recognized at any step, case- and
  accent-insensitive:
  - `AYUDA` / `AGENTE` → human handoff
  - `BAJA` / `STOP` → opt-out
  - `CORREGIR` → correction
  - `BORRAR` → deletion request (DOM-073)
  - `ESTADO` → status of my requests
- **OPW-017 (P0) Status inquiry.**
  - `ESTADO` returns the status of needs linked to *this* contact endpoint only: open,
    under review, shared with organizations (with the date), or resolved, by reference
    code.
  - P1: `DÓNDE` returns directory service points near the resident's area (DOM-043).
  - It never reveals other households sharing the phone without the reference code.
- **OPW-018 (P0) Multiple households per phone.** Before linking to an existing
  household, the bot asks "¿Es para el mismo hogar (CSL-7K3-QF) o para otro?". It never
  silently attaches the report to the last household.
- **OPW-019 (P0) Outside staffed hours.** The bot completes the intake and states when
  staff will review. An urgent flag after hours sends the agreed escalation instructions
  (D8). The bot is never presented as emergency dispatch.

## Identity, abuse, and media

- **OPW-020 (P0) Display identity.**
  - Bot wording uses the campaign's display identity, by default "Metron Reporter"
    (D2/SEC-12).
  - Staff names are never sent to residents.
  - Partner names are sent only when that partner allows it (DOM-078).
- **OPW-021 (P0) Flood detection.**
  - Per-contact limits (e.g., more than 5 new intakes per day) and per-area spikes
    (more than 3× the trailing baseline within 1 hour) create review tasks and slow the
    bot's replies.
  - These detections never deny or delete reports (SEC-11, DOM-065).
- **OPW-022 (P0) Voice notes and media.**
  - The pilot default replies that voice notes and images can't be processed
    automatically and offers buttons or a human.
  - The media is not downloaded.
  - P1, pending D13: staff can play back voice notes from restricted storage, with
    30-day retention.
- **OPW-023 (P0) Free-text safety.** Free text is stored as a restricted, encrypted note,
  retained per NFR-09. The worker never sends it to third-party AI services in the
  pilot.
- **OPW-025 (P0) Urgent path (D8).** If the resident answers "yes" to the urgent
  question:
  - The bot immediately sends the campaign's configured urgent referral content
    (emergency numbers and partner contacts; D15).
  - It creates an urgent review task and handoff for staffed hours.
  - It states that this is not an emergency service and gives no promise of response
    time.
  - Outside staffed hours, it states when staff will review.

## Outbound messaging

- **OPW-030 (P0) Outbox dispatch.** Committed outbox intents are sent through the
  WhatsApp adapter after passing the outbound gate (DOM-071). A blocked intent becomes a
  staff task with the reason.
- **OPW-031 (P0) Window and templates.** Free-form replies are sent only inside the
  24-hour customer-service window. Outside it, only approved templates are used for
  permitted purposes, and a missing template is a terminal, staff-visible failure.
- **OPW-032 (P0) Uncertain sends.** A timeout after submission is marked `uncertain` and
  reconciled through status callbacks or a provider lookup before any resend. The
  worker never blind-resends.
- **OPW-033 (P0) Operational notices.** Templates (registered by the WhatsApp
  contributor; D18) exist for:
  - request received/updated, with the reference code
  - need shared with organizations (DOM-078)
  - status update from staff
  - "do you still need help?" follow-up
  - "did anyone help you?" outcome check
  - sharing-consent request
  - sharing consent withdrawn confirmation (SEC-16)
- **OPW-034 (P0) Rate limiting.** Outbound sends respect provider throughput and tier
  limits with a token bucket. Operational notices take priority over follow-ups.
- **OPW-035 (P0) Surge mode.**
  - When inbox lag exceeds 2 minutes, the worker sends one holding reply per
    conversation ("Recibimos tu mensaje, te responderemos pronto") and processes in
    order (NFR-07).
  - Holding replies are deduplicated per conversation.

## Status events

- **OPW-040 (P0) Monotonic status.** Delivery statuses (sent → delivered → read, or
  failed) never regress because an older event arrives late. Duplicate events are
  ignored.
- **OPW-041 (P0) Failure visibility.** A permanently failed operational notice creates a
  staff task to contact the household another way.

## Evidence, comparison, and review

- **OPW-050 (P0) Comparison rules.**
  - After each confirmed assessment, versioned comparison rules (DOM-061) run against
    candidate observations in the same/adjacent sector and overlapping time window.
  - The rules create links and review tasks.
  - Rules are deterministic, versioned, and replayable.
- **OPW-051 (P0) External evidence ingestion.** `evidence.ingest` takes an accepted
  data-job result, validates its scope, stores the area indicator, and links it as
  context (DOM-064). It creates review tasks only per the configured rules, for example
  an external indicator that disagrees with an area-level cluster of reports.
- **OPW-052 (P0) Stale observation sweep.** Hourly, the worker marks observations on open
  needs as stale when older than the policy age (default 72 hours), and queues a
  follow-up ("¿Sigue sin agua?") if messaging permission allows.

## Follow-ups and scheduled jobs

- **OPW-054 (P0) Share notification.** When a need is first included in a partner list
  view or export, the worker queues the DOM-078 notice once per need. It does not
  re-notify for later shares.
- **OPW-055 (P0) Resident follow-up.** This is the main source of outcome data.
  - On the DOM-037 schedule, and after a partner outcome of `helped` or
    `could_not_reach`, the worker sends a permitted template with buttons: "¿Recibiste
    ayuda?" (Sí / En parte / No) and "¿Todavía lo necesitas?" (Sí / No).
  - Replies record resident outcome facts and refresh, resolve, or reopen needs.
  - A "No" after a partner-reported `helped` creates a review task, not an accusation.
- **OPW-056 (P0) Unassigned escalation.** Every 15 minutes during staffed hours, the
  worker escalates urgent cases unassigned past the threshold (DOM-036).
- **OPW-057 (P0) Unshared and unanswered sweep.** Daily, the worker flags triaged
  shareable needs with no partner in scope, and shared needs with no outcome of any kind
  after the policy period. These go to the coordinator queue.
- **OPW-058 (P0) Data job scheduling.** The worker creates recurring data jobs, such as
  the mock Monitor Ciudad pull every 30 minutes for pilot areas, with idempotency keys
  per window.

## Retention

- **OPW-060 (P0) Retention job.** Runs daily per org. It applies NFR-09 policies (message
  content, anonymous endpoints, precise points, closed cases) via `DB-070`/`DB-071`,
  writes an audit summary, and alerts on failure.

## Operations

- **OPW-070 (P0) Graceful shutdown.** On shutdown the worker stops claiming jobs,
  finishes in-flight work within 30 s, and leaves the rest safe to retry.
- **OPW-071 (P0) Telemetry.** Heartbeat, queue depth and oldest age per job type,
  processing time, retries, failures, outbox age, stuck conversations (no progress for
  more than 10 minutes while waiting on the system), and send failures by error class.
- **OPW-072 (P0) Acceptance scenarios.**
  - Restart in the middle of an intake.
  - A crash after commit but before the job is acknowledged.
  - A duplicate webhook.
  - Out-of-order messages.
  - An interrupted outbound send.
  - Retries exhausted.
  - A post-blackout surge of 10× the normal rate.

  None may lose an accepted report, duplicate a need or follow-up, send a message
  without permission, cross tenants, or fail silently.
