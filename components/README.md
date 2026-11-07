# Component plan

## Architecture

Build one workspace with three runnable processes: web, API, and worker. Domain,
contracts, database, and WhatsApp are shared packages, not separate services.
Dashboards, CRM, analytics, and review are modules within the web/API, rather than
independent applications.

```text
Staff browser → web → api → domain → database → PostgreSQL
                      ↑                 ↑
WhatsApp → webhook in api → durable inbox → worker → domain
                                              ↓
                                 transactional outbox → whatsapp → provider

contracts defines the validated boundary formats used by web, api, and worker
```

The webhook authenticates provider requests and persists an inbox item before
acknowledging receipt. The worker processes inbox items idempotently. Domain
mutations and outbound-message intents commit together; sending occurs afterward.

## Component responsibilities

1. **[web](web/README.md):** Staff login, household CRM, intake, case queues,
   water runs, charging scheduling, review, and aggregate dashboards.
2. **[api](api/README.md):** Authentication, organization authorization, input
   validation, application endpoints, provider webhook handling, and read models.
3. **[worker](worker/README.md):** Resumable intake, inbound message processing,
   retries, outbound delivery, reminders, comparison jobs, and reconciliation.
4. **[domain](domain/README.md):** Case/need lifecycle, resource reservations,
   water delivery, charging completion, urgency decisions, and review rules.
5. **[database](database/README.md):** Relational schema, tenant isolation,
   constraints, transaction primitives, migrations, indexes, and synthetic seeds.
6. **[contracts](contracts/README.md):** Runtime-validated API payloads, event
   schemas, intake versions, enumerations, errors, and quantity/time conventions.
7. **[whatsapp](whatsapp/README.md):** Provider-specific request verification,
   inbound normalization, message submission, template references, and fake adapter.

## Dependency rules

- `contracts` has no dependencies on the other components.
- `domain` may use contracts, but never imports web or provider-specific code.
  Database access is through transaction/repository interfaces supplied by callers.
- `database` implements persistence interfaces and tenant-scoped transactions.
- `whatsapp` depends on contracts, never on case or household persistence.
- `api` and `worker` compose the packages and enforce the required execution context.
- `web` uses API contracts and never connects directly to the database or WhatsApp.
- Neither the API nor worker duplicates domain rules. Both use the same commands.
- Do not add separate analytics infrastructure, a vector database, or AI extraction
  to the initial implementation. Start with relational queries and structured intake.

## First runnable vertical slice

Deliver a local staff workflow with synthetic data:

1. Log in as a staff user of a seeded NGO.
2. Create a household using assisted intake, including an outage observation.
3. Open one case with a water need and a charging need.
4. Reserve water and record a partial delivery; show the outstanding balance.
5. Book charging at a seeded site and record successful or interrupted service.
6. Keep the case open until both needs have reviewed dispositions.

This slice establishes the operational model before adding asynchronous messaging.
Use a development-only identity fixture if necessary; it must be disabled outside
local development and must not replace production authentication.

## Implementation milestones

### 1. Workspace and persistence

- Set up package management, TypeScript configuration, linting, and development commands.
- Provide local PostgreSQL/PostGIS configuration and an environment template.
- Implement organization, membership, household/contact, assessment, observation,
  case, and need migrations with synthetic seed data.
- Establish authenticated organization context and test cross-organization denial.

Exit: a developer can start the application and database using documented commands,
sign in locally, and create/retrieve an assisted-intake case through the UI.

### 2. Fulfillment

- Add resource offers, allocations, water supply, runs/stops, and deliveries.
- Add charging sites, non-overlapping slots, bookings, and sessions.
- Add staff queues and household case history.

Exit: the vertical slice above works; concurrent reservations cannot exceed
capacity, replayed fulfillment commands do not duplicate quantities, and partial
or interrupted fulfillment leaves follow-up visible.

### 3. WhatsApp intake

- Implement and exercise the fake adapter before using provider credentials.
- Add verified webhooks, durable inbox/outbox, idempotent workers, and conversation state.
- Implement Spanish structured intake, confirmation, corrections, opt-out, and handoff.
- Track outreach campaign attribution without treating an invitation as identity proof.

Exit: duplicate, delayed, and retried messages do not create duplicate needs;
interrupted conversations resume; a confirmed intake appears in the staff queue.

### 4. Review and visibility

- Add comparable-observation rules and a human review queue.
- Add aggregate area conditions, freshness, workload, and service-specific metrics.
- Separate staff-reported fulfillment from recipient confirmation.

Exit: conflicting neighborhood reports never automatically deny aid; unknown areas
remain unknown; access restrictions apply to dashboards and exports as well as cases.

### 5. Pilot readiness

- Replace local identity fixtures with production authentication and role management.
- Verify permissions, retention, backup restore, monitoring, failed-job handling,
  and staff fallback procedures.
- Confirm actual water supply suitability, capacity, sites, supported devices,
  operating hours, and escalation owners with the NGO.

Exit: a bounded pilot can be operated by named staff with recovery and support paths.

### Later: multiple organizations

Add scoped sharing agreements, case referrals, recipient acceptance, responsibility
handoffs, revocation, and audit trails. Preserve organization isolation from day one;
do not introduce global beneficiary matching as an incidental feature.

## High-value verification cases

- One organization cannot access another's case by guessing an ID.
- Two households sharing a phone stay distinct.
- Restoration does not close an unmet water need.
- Two coordinators cannot reserve the same last liters or charging capacity.
- Retrying one delivery submission does not double-count delivered water.
- Closing a charging site prevents booking and exposes affected reservations.
- Reports at different times can describe a transition instead of a contradiction.
- A correction retains provenance without creating a second active need unintentionally.

## Planning status

All components are planned, not implemented. Detailed entities and operational
assumptions are in [PLATFORM_PLAN.md](../PLATFORM_PLAN.md). Track implementation
progress against the exit criteria above rather than treating directory creation
as feature completion.
