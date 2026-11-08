# Domain logic

Shared application behavior used by the API and the operational worker, both in the
Python backend. It currently lives at `whatsapp/api/app/domain`. The separate data
worker produces evidence candidates through the internal API. It does not import this
package or change report or need state itself.

## Modules

- **Reports:** confirmed report creation, corrections, reporter keys, and provenance.
- **Needs:** categories, details, and the active → stale → resolved/expired lifecycle.
- **Privacy profiles:** profile-dependent capture, tightening purges, and meeting
  points.
- **Indicators:** area cells, suppression, coverage and confidence labels, and ranking.
- **Providers:** vetting and scope, activities and coverage, alerts, the contact-list
  rule, and share events.
- **Reporter communication:** permissions, the outbound gate, refresh prompts, and
  broadcasts.
- **Review:** comparable claims, explicit links, and human data-quality dispositions.
- **Deferred:** case management and fulfillment (`DOM-090` in
  [REQUIREMENTS.md](REQUIREMENTS.md)).

Commands include `submit_report`, `refresh_need`, `activate_privacy_profile`,
`recompute_cells`, `log_activity`, `export_contact_list`, `send_broadcast`, and
`resolve_review`. Each receives actor/organization context and explicit inputs.

Enforce transaction-sensitive invariants using database constraints and locks through
repository interfaces, not only in-memory checks. Domain state transitions and
audit/outbox intents commit atomically. Keep provider payloads and HTTP concerns out.

Never infer identity from a phone alone, remove a report from aggregates because of
disagreement, count a repeat reporter twice, show an unknown area as zero, store a
field the privacy profile disallows, or let provider activity change a need.

First deliverable: submit a household assessment and create a case with separate
water and charging needs without accidental duplicate active needs on replay.

## Tech stack and packaging

The domain is a plain Python module (`app.domain`) inside the backend package, tested
with pytest.

- It imports no FastAPI, request objects, or WhatsApp provider code.
- Functions take an explicit request context (`ctx`: org, actor, membership, roles),
  a SQLAlchemy session, and validated Pydantic or dataclass inputs. This matches the
  existing `(ctx, db, ...)` pattern.
- It ships inside the one backend image and has no deployment of its own.

Use explicit command and result types, frozen dataclasses for value objects, and
injectable clock and ID generation for tests. Use `Decimal` for liters and integers
for people and device counts; do not
accumulate floating-point rounding errors in quantity totals.

## Command boundaries

Each command receives organization/actor context, validated input, an operation key,
and a transaction context. It loads authorized state, checks business invariants,
updates records, records an audit event, and writes any outbound intent in the same
transaction. External network calls happen only after commit.

For example, `export_contact_list` selects only opted-in reporters with active needs in
a vetted provider's scope, with fields per the profile, and records share events for
exactly those rows. `log_activity` updates coverage without touching needs.
`ingest_external_evidence` validates scope and provenance, and attaches area context
without changing any report.

## States and policy configuration

Keep report, need, provider vetting, activity, conversation, and review state machines distinct.
Define legal transitions explicitly and require a reason for manual overrides.
Version the privacy profile and the policies for ranking, refresh, expiry, and suppression,
so historical indicators keep the rules used at the time. Unknown data must remain distinct from false or zero.

## Verification

Prioritize invariant tests:

- No profile-disallowed fields.
- No contact sharing without consent or outside scope.
- Repeat reporters count once.
- Unknown stays unknown.
- Suppression holds everywhere.
- External evidence and disagreement never remove reports.
Database-backed concurrency checks belong with persistence integration tests rather
than being simulated solely with in-memory repositories.
