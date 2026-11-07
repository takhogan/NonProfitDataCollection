# Domain requirements

Business rules shared by the API and operational worker. Shared context, roles,
decisions, and threat model: [../REQUIREMENTS.md](../REQUIREMENTS.md).

In the pilot, CSL **records, triages, communicates, and shares**. Partners fulfill.
The domain therefore models needs and sharing in depth. Fulfillment appears only
as optional reported outcomes. In-app fulfillment (stock, runs, charging slots) is
deferred (`DOM-090`).

## Command conventions

- **DOM-001 (P0) Explicit context.**
  - Every command receives organization, actor membership, roles, an operation key,
    a clock, and a transaction.
  - A command never takes tenant or actor from its payload.
  - *Accept:* a cross-organization ID returns `not_found`.
- **DOM-002 (P0) Idempotent commands.**
  - Retryable commands (intake, need update, share/export, outcome report, review
    disposition) store their operation key and result.
  - The same key with different input returns `idempotency_conflict`.
- **DOM-003 (P0) Atomic side effects.** The state change, audit event, and outbound
  message intent commit in one transaction. There are no network calls inside commands.
- **DOM-004 (P0) Explicit state machines.**
  - Case, need, conversation, review task, and partner vetting each have a declared
    transition table.
  - An illegal transition returns `invalid_transition`.
  - A manual override requires a reason.
- **DOM-005 (P0) Unknown is not false.** Unknown, absent, and zero stay distinct
  everywhere.

## Intake and observations

- **DOM-010 (P0) Submit assessment.** `submitAssessment` accepts:
  - channel (WhatsApp, phone, assisted)
  - reporting relationship (self, household, other person, area)
  - location
  - power and water observations, each with an observation time and precision
  - zero or more needs
  - permission records
  - questionnaire version

  It creates the assessment and observations. When needs exist, it also links or
  creates the household and case.
  - *Accept:* an area-only report creates no household, person, or case.
- **DOM-011 (P0) Draft vs confirmed.** Bot answers stay a draft until the resident
  confirms the summary. Only confirmed assessments create needs. Abandoned drafts
  (48 hours) keep their partial observations, flagged unconfirmed.
- **DOM-012 (P0) Corrections keep history.** A correction supersedes the earlier record,
  and the prior version stays readable. Correcting a need updates that need under a
  new version, not a second active need.
- **DOM-013 (P0) Observation semantics.**
  - Service types are `electricity` and `piped_water`. Statuses are `available`,
    `unavailable`, `intermittent`, `unknown`.
  - Observation time and outage onset are recorded separately.
  - Drinking-water reserves are a need attribute, not a piped-water status.
- **DOM-014 (P0) Repeat reports.** A repeat report adds to the timeline. A change over
  time is a transition, not a conflict.
- **DOM-015 (P0) Outage episodes.** Optional, correctable grouping by area and time.
  It is never a prerequisite for a need.
- **DOM-016 (P1) Source groups.** Forwarded copies, or the same informant on two
  channels, count as one source.

## Households, people, and contacts

- **DOM-020 (P0) Phone ≠ person.** One endpoint may link to several households.
  Endpoint matches create duplicate candidates and never auto-merge.
  - *Accept:* two households on one shared phone stay distinct.
- **DOM-021 (P0) Minimal household.** A household needs only a random reference code
  (e.g. `MR-7K3-QF`), an area, and an optional estimated member count. Names and
  precise location are optional.
- **DOM-022 (P0) Safe-to-contact.** Contacts record `is_safe_to_contact` and an optional
  preferred contact window. Outbound intents check it. A contact that is not safe to
  contact is excluded from partner lists (`DOM-075`).
- **DOM-023 (P0) Merges.** Merges need a reviewer proposal and coordinator approval.
  They are reversible and keep provenance.
- **DOM-024 (P1) Location history.** A move creates a new location validity interval.

## Cases and needs

- **DOM-030 (P0) Need categories.** Each need belongs to one category:
  - `water_drinking`
  - `water_other`
  - `charging`

  Drinking and other-use water are separate needs, never merged. Each need has a
  period, urgency with reasons, a status, and optional quantity:
  - water: liters requested, or people to serve
  - charging: device count

  Units are never mixed.
- **DOM-031 (P0) Need status:**

  ```text
  open → triaged → resolved
  ```

  Branches: `on_hold`, `withdrawn` (by the resident), and `expired` (no confirmation
  of need after the policy period).
  - Sharing state is a separate attribute (`DOM-075`).
  - Partner-reported and resident-reported outcomes are facts attached to the need.
    They inform a CSL disposition but do not change status by themselves.
  - `resolved` requires a disposition reason: `resident_confirmed_helped`,
    `resident_no_longer_needs`, `partner_reported_and_no_reply`, `duplicate`, or
    `other` with a note.
- **DOM-032 (P0) Case closure.** A case closes only when every need is resolved,
  withdrawn, or expired. Service restoration never closes a need.
  - *Accept:* piped water restored → the `water_drinking` need stays open. One need
    resolved → the others stay open.
- **DOM-033 (P0) Urgency.**
  - Urgency is `urgent`, `high`, or `routine`, set or confirmed by staff from
    declared inputs:
    - remaining drinking water
    - waiting time
    - stated urgency
    - access barriers (cannot leave home, no containers)
    - presence of vulnerable members (yes/no only)
  - The bot's suggestion is stored separately from the human decision.
  - Outage duration or neighborhood consensus alone never sets priority.
- **DOM-034 (P0) Versioned policy.** Triage, urgency suggestion, escalation thresholds,
  stale-need period, and expiry period are versioned org data. Each decision records
  the version in force.
- **DOM-035 (P0) Repeat demand.**
  - A request in a new period is new demand.
  - A request that overlaps an open need of the same category updates that need
    (refreshing `last_confirmed_at`) instead of duplicating it.
- **DOM-036 (P0) Assignment and escalation.** A case has at most one owner, and
  reassignment records the reason. Urgent cases unassigned past the threshold (default
  2 hours in staffed hours) escalate.
- **DOM-037 (P0) Follow-up.**
  - A follow-up asks the resident whether the need remains and whether anyone helped.
    It runs after a need is shared, and periodically while the need is open (default
    every 72 hours, max 3 attempts).
  - Replies refresh, resolve, or reopen the need.
  - No reply leads to `expired` only after the policy period, never sooner.

## Need details

- **DOM-040 (P0) Water detail.**
  - Intended use is implied by the category.
  - People to serve, remaining supply (`none`/`little`/`some`/`unknown`, plus
    optional days left).
  - Whether they have containers, and whether they need help receiving.
  - Delivery landmark and preferred window.
  - All fields are optional except the category.
- **DOM-041 (P0) No safety inference.** The platform never records or implies that any
  water is safe to drink. It records only what the resident needs.
- **DOM-042 (P0) Charging detail.**
  - Device types (phone, power bank, other with text) and counts.
  - Whether they have a charger or cable.
  - Whether they can reach a site, and access assistance needed.
  - Preferred times.
- **DOM-043 (P1) Service directory.**
  - Coordinators maintain a list of partner-provided service points: water
    distribution points and charging places, with area, hours, status, and
    last-checked time.
  - The bot can share the points relevant to a resident's area and need.
  - The directory only gives information; it does not reserve anything.

## Sharing with partners

- **DOM-070 (P0) Permission records.** Messaging permission, data-processing notice
  acknowledgement, and **sharing consent** are separate records, each with a purpose,
  notice version, and capture time. Sharing consent is optional and its wording is
  specific (SEC-16).
- **DOM-071 (P0) Outbound gate.** Every outbound intent declares its purpose and checks:
  - permission
  - opt-out
  - safe-to-contact
  - the messaging window or template requirement

  Blocked intents become staff tasks.
- **DOM-072 (P0) Opt-out and withdrawal.**
  - Opt-out stops optional outreach.
  - Withdrawing sharing consent removes the household from all partner lists and
    queues a resident notice (SEC-16).
  - Both trigger retention handling.
- **DOM-073 (P1) Deletion request.** Creates a task, runs anonymization, and keeps
  aggregates and required audit records.
- **DOM-075 (P0) Contactable list.** A need appears on a partner's list only when all of
  these hold:
  - the household has active sharing consent and is safe to contact
  - the need is `triaged`, not resolved, withdrawn, or expired, and marked
    `shareable` by staff
  - the need's category and area are in the partner's scope
  - the partner organization is `vetted`

  Fields are the minimum per D17 (proposed below). The list never includes observation
  history, notes, review flags, other needs out of scope, or names unless the resident
  chose to give one.
  - Proposed minimum fields: reference code, sector, landmark, category, quantity or
    people, urgency, preferred window, container/access notes, and phone.
- **DOM-076 (P0) Partner vetting.**
  - Partner organizations move `unvetted → vetted → suspended`, and only an org admin
    may change this, with a reason.
  - Vetting records the responsible contact, the data-handling statement version, and
    the scope.
  - Suspension immediately removes list access and expires the partner's export links.
- **DOM-077 (P0) Share events.** Every list view and export records a share event: the
  partner, the user, which needs (IDs), the fields, and the time. A need's sharing
  attribute shows which partners received it and when.
  - *Accept:* a coordinator can answer "which partners received household MR-7K3-QF's
    data?"
- **DOM-078 (P0) Resident informed.** The first time a need is shared, the resident is
  told that their request is now visible to organizations that may help in their area,
  and that CSL does not control whether or when those organizations respond. Partner
  names are not sent unless the partner agrees (configurable per partner).
- **DOM-079 (P1) Partner outcomes.**
  - A partner user may record an outcome on a listed need: `contacted`, `helped`
    (with an optional quantity), `could_not_reach`, `not_able_to_help`.
  - Each outcome is a fact with its source and time, never a status change.
  - Outcomes `helped` and `could_not_reach` trigger a resident follow-up (DOM-037).

## Evidence and review

- **DOM-060 (P0) Separation.** Evidence status (`unreviewed`, `corroborated`,
  `disputed`, `unresolved`), need urgency, and the shareable/resolution decisions are
  separate fields. No rule writes from evidence status to them.
- **DOM-061 (P0) Comparison candidates.**
  - Versioned rules propose links between observations: `supports`,
    `potentially_conflicts`, `possible_duplicate`, `supersedes`.
  - Rules apply only to observations with compatible service, subject scope, area,
    and overlapping time.
  - Each link stores the rule version and reasons.
  - *Accept:* the same household, unavailable at 10:00 and available at 15:00, is a
    transition. Two households in the same sector with different statuses at the same
    time get a link and a review task, and no need changes.
- **DOM-062 (P0) Review tasks.** Created for:
  - potential conflicts and duplicate candidates
  - uncertain locations
  - stale observations on open needs
  - unparsed free text
  - floods (SEC-11)
  - resident disputes of a partner-reported outcome
  - external evidence of interest

  Each task carries its reasons and evidence.
- **DOM-063 (P0) Dispositions.** Each disposition records the rationale, evidence,
  reviewer, and an optional review-after date. New evidence reopens it.
- **DOM-064 (P0) External evidence is context.** Monitor Ciudad and satellite indicators
  link at area scope. They never change a need, a shareable flag, or evidence status
  directly.
- **DOM-065 (P0) No automatic denial or exclusion.** No rule may resolve, expire early,
  downgrade, or mark a need unshareable because of disagreement, report frequency, a
  shared phone, missing evidence, or external indicators. A property-based test asserts
  this across commands.

## Deferred: in-app fulfillment (P2)

- **DOM-090 (P2) Fulfillment management.** If CSL or a partner later runs fulfillment in
  this platform, reinstate the following from PLATFORM_PLAN.md:
  - water supply release and use compatibility
  - locked allocations
  - delivery runs, stops, partial deliveries, and reconciliation
  - charging sites, non-overlapping slots, bookings, walk-ins, sessions, and site
    closure

  These carry the original invariants: no over-allocation, idempotent fulfillment,
  and booking ≠ completion. IDs `DOM-044`–`DOM-059` are reserved for this work.
