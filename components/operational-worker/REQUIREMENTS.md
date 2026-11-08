# Operational worker requirements

Asynchronous processing in the Python backend:

- the WhatsApp reporting conversation
- outbound messages (refresh prompts, broadcasts)
- status events
- indicator refresh and coverage
- provider alerts
- external evidence ingestion
- comparison rules
- retention

Shared context: [../REQUIREMENTS.md](../REQUIREMENTS.md).

## Processing guarantees

- **OPW-001 (P0) No lost accepted input.** Every inbox item reaches a terminal state:
  processed, ignored with a reason, or failed and visible to staff. Pending-record
  scans recover items whose job was lost.
- **OPW-002 (P0) Idempotent handlers.** Duplicate jobs, retries after commit, and replays
  create no duplicate reports, needs, messages, alerts, or evidence.
- **OPW-003 (P0) Per-conversation ordering.** Messages in a conversation are processed in
  order, serialized across replicas. Out-of-order provider events are reordered within
  5 s.
- **OPW-004 (P0) Retries.** Transient failures back off (max 8 attempts or 1 hour).
  Permanent failures are terminal, with redacted reasons. Failed items are listed for
  staff to replay.
- **OPW-005 (P0) Tenant context.** Org context is loaded from the persisted record, and
  the worker runs under the RLS-bound worker role.
- **OPW-006 (P0) Jobs.** Jobs are application-owned PostgreSQL rows, claimed with
  `FOR UPDATE SKIP LOCKED`, each with a lease, attempt count, and next-run time
  (decision D19).

## WhatsApp reporting conversation

The conversation engine runs the questionnaire definition (`CON-030`) as a state
machine. It lives in this repo. The production Meta adapter comes from the WhatsApp
contributor, built against `WA-001`. Tests use the fake adapter.

- **OPW-010 (P0) Entry.**
  - The first message (with or without a campaign token) starts or resumes a
    conversation.
  - The token sets attribution only.
- **OPW-011 (P0) Notice.**
  - The bot introduces itself as **Metron Reporter**, names the operating NGO as
    responsible for the data, and explains:
    - what is collected, and that it is used to show **which areas need help** to
      organizations that can act
    - that Metron Reporter does not deliver aid
    - that reporting does not guarantee help

    It offers a human.
  - It records the notice acknowledgement before any personal question.
- **OPW-012 (P0) Structured questions.**
  - Buttons and lists where possible, with numbered fallback. "No sé" is always
    allowed.
  - Free text at a choice step is re-asked once, then stored as a restricted note and
    flagged.
- **OPW-013 (P0) Area and location by profile.**
  - Area is resolved from the parish/sector list, with alias matching. Ambiguous input
    offers up to 3 candidates. Unresolvable input becomes a location review task.
  - `meeting_point` profile: after the sector, the bot offers that sector's meeting
    points ("¿Cuál punto de encuentro te queda más cerca?"), plus "ninguno cerca".
  - `address` profile: it asks for an address or landmark, and optionally a shared
    location.
  - In protective mode, it never asks for name or address, and a shared GPS location
    is reduced to the area and the point discarded.
- **OPW-014 (P0) Report content.** Electricity and piped-water status with times; needs
  (drinking water, other water, charging) with details; urgency.
- **OPW-015 (P0) Permissions.** After the needs, the bot asks three separate yes/no
  questions:
  1. "¿Podemos escribirte cada pocos días para saber si sigue el problema?" (refresh)
  2. "¿Quieres recibir avisos de ayuda disponible en tu zona?" (area info)
  3. "¿Aceptas que organizaciones verificadas que ayudan en tu zona vean tu número
     para contactarte?" (contact list)

  No to all three still records the report.
- **OPW-016 (P0) Summary and confirm.**
  - The resident confirms or fixes the summary. Only confirmed reports count
    (`DOM-011`).
  - The confirmation says the report helps show where help is needed, and repeats which
    permissions were given.
- **OPW-017 (P0) Pause and resume.** A conversation resumes within 48 hours. "Menú" and
  "Atrás" work at any step.
- **OPW-018 (P0) Global commands.** Recognized at any step, case- and accent-insensitive:
  - `AYUDA` → human
  - `BAJA` → stop all messages
  - `CORREGIR` → fix the last report
  - `ACTUALIZAR` → refresh status
  - `DÓNDE` → active public provider activities near the resident's area
  - `PERMISOS` → review or withdraw individual permissions
  - `BORRAR` → deletion request
- **OPW-019 (P0) Shared phones.** In the `standard` profile with household records, the
  bot asks which household a repeat report is for. In protective mode, repeat reports
  update the reporter's own latest report, and the bot says so.
- **OPW-020 (P0) Display identity.** The bot uses the campaign's display identity. Staff
  names are never sent. Provider names are sent only if the provider allows it.
- **OPW-021 (P0) Urgent path (D8).**
  - A "yes" to urgent sends the configured referral content (D15) immediately.
  - It creates a coordinator review task for staffed hours.
  - It states this is not an emergency service.
- **OPW-022 (P0) Media.** Voice notes and images are not downloaded. The bot explains this
  and offers buttons or a human. Playback is a P1 decision (D13).
- **OPW-023 (P0) Free text.** Free text is stored as a restricted, encrypted note per
  NFR-09. It is not sent to third-party AI services, with one opt-in exception
  (amended 2026-11-08):
  - With `OPENAI_EXTRACTION` on (off by default), a short typed answer that the
    deterministic parser cannot read may be sent to OpenAI with the question it
    answers, to fill the report fields.
  - It is redacted first (phone numbers, e-mails, links, ID numbers; max 280
    characters). Address and landmark answers, names, consent answers and the
    sender's number are never sent.
  - The model answers in a fixed JSON schema. Code validates every value and
    writes the rows; the model never chooses ids or writes SQL.
  - Enabling it needs the operating NGO's agreement.
- **OPW-024 (P0) Abuse detection.** Per-contact and per-area spikes create review tasks
  and slow replies. They never delete or exclude reports (`DOM-073`).

## Outbound messaging

- **OPW-030 (P0) Outbox dispatch.** Committed intents are sent after the outbound gate
  (`DOM-061`). Blocked intents are dropped and counted.
- **OPW-031 (P0) Window and templates.** Free-form only inside the 24-hour window.
  Otherwise approved templates only. A missing template is a visible terminal failure.
- **OPW-032 (P0) Uncertain sends.** Timeouts after submission are reconciled, never
  blindly resent.
- **OPW-033 (P0) Templates** (registered by the WhatsApp contributor; D18):
  - report received
  - refresh prompt
  - area information broadcast
  - permission changed confirmation
  - opt-out confirmation
- **OPW-034 (P0) Rate limits.** Token bucket per provider tier. Replies to residents take
  priority over refresh prompts, which take priority over broadcasts.
- **OPW-035 (P0) Surge mode.** When lag exceeds 2 minutes, the bot sends one holding
  reply per conversation and processes in order.

## Status events

- **OPW-040 (P0) Monotonic status.** Delivery statuses never regress, and duplicates are
  ignored.

## Indicators, coverage, and alerts

- **OPW-045 (P0) Indicator refresh.**
  - Confirmed reports, review dispositions, expiries, and external evidence mark
    affected area cells dirty.
  - A recompute job refreshes them within NFR-06 (5 minutes).
  - A full rebuild runs nightly and on method-version change.
- **OPW-046 (P0) Coverage refresh.** Activity changes and indicator changes recompute
  coverage (`DOM-052`). Activities unconfirmed for 7 days are marked `unconfirmed`.
- **OPW-047 (P0) Alert evaluation.**
  - After each refresh, the worker evaluates subscriptions (`DOM-055`).
  - It sends deduplicated aggregate-only alerts through the configured channel (D26;
    default email via a transactional email provider).
  - Alerts contain no personal data.
- **OPW-048 (P0) Public snapshot.** When the public dashboard is enabled, the worker
  publishes the public cells (`DOM-080`) on the profile's delay schedule.

## Evidence and review

- **OPW-050 (P0) Comparison rules.** After each confirmed report, versioned rules
  (`DOM-071`) run against compatible observations and create review tasks.
- **OPW-051 (P0) External evidence ingestion.** Accepted data-job results are stored as
  area context layers (`DOM-074`). They update confidence labels and may open review
  tasks.
- **OPW-052 (P0) Outlier detection.** Cells that change sharply on few reporters are
  flagged for review, and their confidence is lowered until reviewed.

## Reporter refresh and broadcasts

- **OPW-055 (P0) Refresh prompts.** On the `DOM-062` schedule, the worker sends refresh
  templates with buttons: "¿Sigue sin luz/agua?" and "¿Todavía necesitas …?". Replies
  update observations and needs.
- **OPW-056 (P0) Need lifecycle sweep.** Hourly, the worker moves needs to `stale` or
  `expired` (`DOM-021`) and marks affected cells dirty.
- **OPW-057 (P0) Broadcast delivery.** Approved broadcasts (`DOM-063`) are expanded to
  permitted recipients at send time. Per-reporter weekly limits apply. The final
  recipient count is recorded.
- **OPW-058 (P0) Data job scheduling.** Recurring data jobs run with per-window
  idempotency keys, for example mock Monitor Ciudad every 30 minutes for pilot areas.

## Retention

- **OPW-060 (P0) Retention and profile purges.**
  - Runs daily per org.
  - Applies NFR-09 and profile tightening purges (`DOM-032`) via `DB-070`/`DB-071`.
  - Writes audit counts and alerts on failure.
  - Rotates pseudonymous reporter keys per the profile.

## Operations

- **OPW-070 (P0) Graceful shutdown.** On SIGTERM: stop claiming, finish within 30 s, and
  leave the rest safe to retry.
- **OPW-071 (P0) Telemetry.**
  - Heartbeat; job depth and oldest age per type; processing time; retries and
    failures; outbox age.
  - Stuck conversations, indicator staleness, and alert send failures.
- **OPW-072 (P0) Acceptance scenarios.**
  - Restart mid-intake.
  - A crash after commit.
  - A duplicate webhook.
  - Out-of-order messages.
  - An interrupted send.
  - Retries exhausted.
  - A 10× surge.
  - A profile tightening in the middle of a run.

  None may lose a report, double-count a reporter in a cell, send without permission,
  cross tenants, leak personal data in alerts, or fail silently.
