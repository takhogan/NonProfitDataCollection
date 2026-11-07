# Domain logic

Shared application behavior used by the API and TypeScript operational worker.
Python produces evidence candidates through the internal API; it does not import
this package or independently implement case/assistance state transitions.

## Modules

- **Intake:** confirmed assessment creation, corrections, household linkage, and provenance.
- **Cases and needs:** assignments, urgency reasons, separate need states, and closure rules.
- **Need details:** drinking water, other-use water, and charging details passed to partners.
- **Sharing:** partner vetting and scope, the contactable list rule, share events, and outcomes.
- **Follow-up:** resident follow-ups that refresh, resolve, or reopen needs.
- **Deferred:** water/charging fulfillment (`DOM-090` in [REQUIREMENTS.md](REQUIREMENTS.md)).
- **Review:** comparable claims, explicit supporting/conflicting links, and human dispositions.
- **Permissions:** allowed contact purposes and optional sharing scope.

Commands include `submitAssessment`, `assignCase`, `setNeedShareable`,
`exportPartnerList`, `recordPartnerOutcome`, `recordResidentOutcome`,
`resolveNeed`, and `resolveReview`. Each receives actor/organization context and explicit inputs.

Enforce transaction-sensitive invariants using database constraints and locks through
repository interfaces, not only in-memory checks. Domain state transitions and
audit/outbox intents commit atomically. Keep provider payloads and HTTP concerns out.

Never infer identity from a phone alone, convert geographic disagreement into an
automatic denial, treat a partner-reported outcome as resolution, share without
consent, or close other unmet needs when one need is resolved. Evaluate repeated requests within their requested period.

First deliverable: submit a household assessment and create a case with separate
water and charging needs without accidental duplicate active needs on replay.

## Proposed tech stack and packaging

A plain TypeScript workspace library, compiled with `tsc` and tested with Vitest.
No HTTP framework, queue library, database driver, or geospatial dependency belongs
here. It ships inside the API and operational-worker images and has no deployment
or network port of its own.

Use explicit command/result types, immutable value objects where useful, and injected
repository, transaction, clock, and ID-generation interfaces. Use fixed-scale quantities
or integer subunits for water accounting and integers for device sessions; do not
accumulate floating-point rounding errors in quantity totals.

## Command boundaries

Each command receives organization/actor context, validated input, an operation key,
and a transaction context. It loads authorized state, checks business invariants,
updates records, records an audit event, and writes any outbound intent in the same
transaction. External network calls happen only after commit.

For example, `exportPartnerList` selects only consented, in-scope, shareable needs for a
vetted partner, and records share events for exactly those rows. `recordPartnerOutcome`
adds an outcome fact and queues a resident follow-up without changing need status.
`ingestExternalEvidence` validates scope/provenance and links evidence for review,
without declaring a household ineligible.

## States and policy configuration

Keep case, need, partner vetting, conversation, and review state machines distinct.
Define legal transitions explicitly and require a reason for manual overrides.
Version NGO policies for triage, urgency, follow-up, and expiry so historical decisions retain the
rules used at the time. Unknown data must remain distinct from false or zero.

## Verification

Prioritize state-transition tests and invariants: no sharing without consent or
outside scope, partner outcomes never resolve needs alone, one resolved need does not
close another, and external evidence cannot automatically deny or exclude.
Database-backed concurrency checks belong with persistence integration tests rather
than being simulated solely with in-memory repositories.
