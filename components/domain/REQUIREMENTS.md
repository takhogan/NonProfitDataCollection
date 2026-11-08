# Domain requirements

Business rules shared by the API and operational worker in the Python backend
(`app.domain`). Shared context, roles, privacy profiles, and decisions:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

The core flow is **reports → area indicators → providers act**. The operating NGO
does not manage individual cases in the pilot (`DOM-090`).

## Command conventions

- **DOM-001 (P0) Explicit context.**
  - Every command takes a context (org, actor, roles, privacy profile version), an
    operation key, a session, and a clock.
  - Tenant and actor never come from the payload.
  - Other-org IDs return `not_found`.
- **DOM-002 (P0) Idempotency.** Retryable commands store their operation key, a digest
  of the request, and the result. The same key with different input returns
  `idempotency_conflict`.
- **DOM-003 (P0) Atomic side effects.** State change, audit event, and outbound intent
  commit in one transaction. There are no network calls inside commands.
- **DOM-004 (P0) Explicit state machines.** Report, need, review task, provider vetting,
  activity, and conversation each have a declared transition table.
- **DOM-005 (P0) Unknown is not false.** Unknown, absent, and zero stay distinct in
  reports and aggregates.

## Reports and observations

- **DOM-010 (P0) Submit report.** `submitReport` accepts:
  - channel and reporting relationship (self, household, other person, area)
  - area, plus profile-dependent location detail (`DOM-031`)
  - `electricity` and `piped_water` observations, each with observation time and
    precision
  - zero or more needs
  - permissions
  - the questionnaire version

  *Accept:* an area-only report stores no personal data.
- **DOM-011 (P0) Draft vs confirmed.** Bot answers stay a draft until the reporter
  confirms. Only confirmed reports feed aggregates. Abandoned drafts contribute nothing.
- **DOM-012 (P0) Corrections keep history.**
  - A correction supersedes the earlier report.
  - Aggregates use the latest version.
  - The prior version is kept per retention rules.
- **DOM-013 (P0) Observation semantics.**
  - Statuses are `available`, `unavailable`, `intermittent`, `unknown`.
  - Observation time and outage onset are recorded separately.
  - Drinking-water reserves are a need attribute, not a piped-water status.
- **DOM-014 (P0) Repeat reports.**
  - Repeat reports from the same reporter are linked through a **pseudonymous reporter
    key**: an org-scoped HMAC of the contact endpoint, rotated per the profile.
  - They update that reporter's current state instead of counting twice.
  - A change over time is a transition, not a conflict.
  - *Accept:* the same phone reporting "no water" three times in a day counts as one
    reporter in that day's aggregate.
- **DOM-015 (P0) Shared phones.** In the `standard` profile with household records, a
  shared phone may represent several households, and the reporter chooses which one.
  In the `protective` profile, the reporter key counts reporters, not households, and
  indicators label the unit honestly ("reportantes").
- **DOM-016 (P0) Outage episodes.** Optional, correctable grouping by area and time.
- **DOM-017 (P1) Source groups.** Forwarded copies, or the same informant on two
  channels, count as one source.

## Needs

- **DOM-020 (P0) Need record.** A need belongs to a report:
  - category (`water_drinking`, `water_other`, `charging`)
  - people affected (optional)
  - quantity (optional): liters for water, device count for charging
  - remaining supply (`none`/`little`/`some`/`unknown`)
  - stated urgency
  - access notes (cannot leave home, no containers)
  - preferred times
- **DOM-021 (P0) Need lifecycle.**

  ```text
  active → stale → resolved_by_reporter | withdrawn | expired
  ```

  - A need goes `stale` with no confirmation after the refresh period (default 72
    hours), and `expired` after the expiry period (default 14 days).
  - Refresh replies ("¿Todavía lo necesitas?") reactivate the need or resolve it.
  - Service restoration never resolves a need.
- **DOM-022 (P0) No dispatch semantics.** Needs have no assignment, allocation, or
  closure workflow. Provider activity in an area never changes a need's state. Only the
  reporter, or expiry, does.
- **DOM-023 (P0) Urgency is reported, not judged.** Stated urgency and its inputs are
  stored as reported. Coordinators may flag an urgent report for review (D8), but
  aggregates never re-weight individuals by staff judgment.

## Privacy profile enforcement

- **DOM-030 (P0) Profile as policy.** The privacy profile is a versioned org policy with
  these settings:
  - names allowed
  - location mode (`meeting_point` / `address`)
  - GPS allowed
  - reporter phone retention
  - household records allowed
  - contact-list fields
  - public dashboard level, *k*, and delay
  - aggregate *k*

  Every command reads the active version. Each report records the version it was
  collected under.
- **DOM-031 (P0) Location capture by profile.**
  - `meeting_point` mode: the reporter picks a meeting point in their sector from a
    short list, or "none nearby".
  - `address` mode: an encrypted address or landmark is captured, plus an optional GPS
    point.
  - *Accept:* in protective mode, the schema rejects name, address, or GPS fields.
- **DOM-032 (P0) Tightening.** Activating a stricter profile queues a purge of fields the
  new profile disallows. It runs within 24 hours and is audited with counts.
- **DOM-033 (P0) Loosening.** A looser profile applies only to reports collected under
  the new notice version. Existing data is never enriched.
- **DOM-034 (P0) Meeting points.**
  - Coordinators manage meeting points per sector: name, type, and a description of a
    public place.
  - A meeting point holds no personal data.
  - Deactivating one keeps references, labelled inactive.

## Area indicators

- **DOM-040 (P0) Indicator cells.** For each area (sector and parish) × category or
  service × time bucket (6 hours, 24 hours, 7 days), compute:
  - active needs
  - distinct reporters (and households in the `standard` profile)
  - people affected (sum of known values, plus the count of needs where it is unknown)
  - urgency mix and remaining-supply mix
  - service status mix
  - freshness (newest confirmed observation)
  - the share of reports pending review
- **DOM-041 (P0) Unknown coverage.** An area with no reports in the bucket is `unknown`,
  never zero need or "service OK". Indicators carry a coverage label: `none`, `thin`
  (< k), or `reported`.
- **DOM-042 (P0) Confidence label.** Every cell has a transparent confidence label, not a
  numeric truth score, derived from:
  - the number of independent sources
  - review status
  - freshness
  - agreement with external context (Monitor Ciudad, satellites)

  Labels: `low`, `medium`, `high`, each with stated reasons.
- **DOM-043 (P0) Need ranking.**
  - "Areas of greatest need" is ordered by declared criteria shown to the user. The
    default order is urgent active needs, then active needs per reporter, then age of
    the oldest unmet need, then freshness.
  - The method is versioned, and the version is shown.
  - No hidden weights.
- **DOM-044 (P0) Suppression.** Cells under *k* distinct reporters or households are
  suppressed or merged up to the parent area, per SEC-10. Suppression runs before any
  view, export, or API response.
- **DOM-045 (P0) Separate layers.** External indicators are a separate layer from
  resident reports, with their own source labels. They never add to or subtract from
  report counts.
- **DOM-046 (P0) Reproducibility.** Each indicator snapshot records its method version,
  input watermark (the latest included report), and profile version, so a published
  number can be explained later.
- **DOM-047 (P1) Trends.** Week-over-week change per area and category, with alerts on
  significant rises (`DOM-055`).

## Providers

- **DOM-050 (P0) Provider organizations.**
  - Vetting moves `unvetted → vetted → suspended`, and only an org admin can change it,
    with a reason.
  - Each has a scope (areas × categories), a responsible contact, and a statement
    version.
  - Suspension immediately revokes contact-list access and API keys.
- **DOM-051 (P0) Activity log.** Providers record what they are doing where:
  - type: `water_distribution_point`, `water_delivery`, `charging_point`, `other`
  - category served, and areas served
  - schedule (one-off or recurring, with hours)
  - optional capacity (liters per day, devices per day)
  - optional public location: a meeting point or public site, never a household
  - status (`planned`, `active`, `paused`, `ended`)
  - last-confirmed time

  Activities not confirmed for 7 days are shown as `unconfirmed`.
- **DOM-052 (P0) Coverage gaps.**
  - An area × category is `uncovered` when it has active need above a threshold and no
    `active` provider activity serving it.
  - It is `covered` when it does, and `unknown` when there is no data.
  - Coverage says nothing about whether needs were met.
- **DOM-053 (P0) Activity visibility.** All providers in the tenant see activity entries:
  organization name, type, areas, schedule, status. Providers can mark an entry
  internal-only, in which case it counts toward coverage but its details are hidden
  from other providers. Public visibility follows `DOM-081`.
- **DOM-054 (P0) Contact list.** A vetted provider sees a reporter on its opt-in contact
  list only when all of these hold:
  - the reporter granted list consent (SEC-16)
  - the reporter has an `active` need in the provider's scope
  - the profile allows contact lists

  Fields follow the profile: protective shows alias, sector, meeting point, and phone;
  standard shows name, address, and phone. Every view or export writes share events.
- **DOM-055 (P0) Alert subscriptions.** A provider user subscribes to an area set ×
  category with a trigger:
  - new urgent needs
  - active needs rising above N
  - an area becoming uncovered
  - a large external outage signal

  Alerts are aggregate-only, suppressed, and deduplicated per subscription per window
  (default 6 hours). Delivery channel per D26.

## Reporter communication

- **DOM-060 (P0) Permissions.**
  - Separate records for: notice acknowledgement, refresh prompts, area broadcasts, and
    contact-list inclusion.
  - Each records its purpose, notice version, and time, and can be withdrawn.
- **DOM-061 (P0) Outbound gate.** Every outbound intent declares a purpose. The gate
  checks permission, opt-out, the messaging window or template, and rate limits.
  Blocked intents are dropped and counted, and do not create staff tasks.
- **DOM-062 (P0) Refresh prompts.**
  - A permitted reporter with an `active` or `stale` need is asked, at most every 72
    hours and at most 3 times per need, whether the service is still out and whether
    they still need help.
  - Replies update observations and needs.
- **DOM-063 (P0) Area information broadcasts.**
  - A coordinator can send provider activity information to permitted reporters with
    matching active needs in the activity's areas. Example: "Punto de agua en Plaza X,
    sáb 8–12, organizado por Y".
  - The coordinator approves the text, which comes from a template.
  - Provider names are included only if the provider allows it.
  - Each reporter receives at most 2 broadcasts per week.
- **DOM-064 (P0) Opt-out.** `BAJA` stops all outbound messages except the confirmation.
  Withdrawing a single permission stops only that purpose.

## Data quality review

- **DOM-070 (P0) Review tasks.** Created for:
  - duplicate candidates
  - same-area conflicting observations at overlapping times
  - unresolved locations
  - floods and coordinated bursts
  - outlier cells (a sudden spike from few reporters)
  - urgent-flagged reports (D8)
  - unparsed free text
- **DOM-071 (P0) Comparison rules.** Versioned rules compare only compatible service,
  scope, area, and overlapping time. They store the rule version and reasons. The same
  reporter changing status over time is a transition.
- **DOM-072 (P0) Dispositions.** Each records rationale, reviewer, and an optional
  review-after date. Possible outcomes:
  - `valid`
  - `duplicate` (merged, counted once)
  - `spam` (excluded from aggregates, with a reason)
  - `location_corrected`
  - `unresolved`
- **DOM-073 (P0) No exclusion by disagreement.**
  - Reports are never excluded from aggregates automatically because of disagreement
    with neighbors, external data, report frequency, or a shared phone.
  - Unreviewed and disputed reports still count; they lower the cell's confidence label.
  - Only a human `duplicate` or `spam` disposition removes a report.
  - A property test asserts this across commands.
- **DOM-074 (P0) External evidence is context.** Monitor Ciudad and satellite indicators
  link at area scope. They affect confidence labels and may open review tasks, but
  never change report or need state.

## Public dashboard

- **DOM-080 (P0) Public cells.** Derived from indicator cells using the profile's public
  level, *k*, and delay. Only these fields are included:
  - status mix
  - need counts by category (banded, e.g. "10–24")
  - coverage label
  - freshness
- **DOM-081 (P0) Public provider activity.** Only activities a provider marked public
  are shown, with organization name, type, area, schedule, and public location.

## Deferred

- **DOM-090 (P2) Case management module.** An optional per-org module for NGOs that want
  to follow individual households:
  - household records, cases, assignment, queues, closure, and handoff
  - optionally, in-app fulfillment (allocations, delivery runs, charging slots, as
    designed in PLATFORM_PLAN.md)

  It must respect the privacy profile.
- **DOM-095 (P2) Cross-tenant aggregates.** Combined indicators across operating NGOs
  under sharing agreements. Each tenant's suppression applies before combination.
