# Platform requirements

Requirements draft · 7 November 2026 · revision 3: data aggregation platform

This document holds the context shared by every component: purpose, users, roles,
privacy profiles, threat model, non-functional requirements, and decisions. Each
component's `REQUIREMENTS.md` lists that component's features and acceptance criteria:

| Component | Requirements | Prefix |
|---|---|---|
| Web | [web/REQUIREMENTS.md](web/REQUIREMENTS.md) | `WEB` |
| API | [api/REQUIREMENTS.md](api/REQUIREMENTS.md) | `API` |
| Operational worker | [operational-worker/REQUIREMENTS.md](operational-worker/REQUIREMENTS.md) | `OPW` |
| Data worker | [data-worker/REQUIREMENTS.md](data-worker/REQUIREMENTS.md) | `DAW` |
| Domain | [domain/REQUIREMENTS.md](domain/REQUIREMENTS.md) | `DOM` |
| Database | [database/REQUIREMENTS.md](database/REQUIREMENTS.md) | `DB` |
| Contracts | [contracts/REQUIREMENTS.md](contracts/REQUIREMENTS.md) | `CON` |
| WhatsApp | [whatsapp/REQUIREMENTS.md](whatsapp/REQUIREMENTS.md) | `WA` |

Where this file and [PLATFORM_PLAN.md](../PLATFORM_PLAN.md) differ, this file wins.

## Purpose

**This is a data aggregation platform, not an aid dispatch platform.**

1. It collects reports of power and water outages, and of household needs, from
   residents (WhatsApp bot, assisted intake) and from external sources (Monitor Ciudad,
   satellites).
2. It turns those reports into **area-level indicators of need**: where people lack
   electricity, piped water, drinking water, or charging, how many, how urgently, how
   recently, and how confident the data is.
3. It lets **providers** (NGOs, water distributors, charging hosts, relief groups) log
   in, see which areas need help, and act with their own resources. Providers also log
   what they are doing where, so everyone can see covered and uncovered areas.

The operating NGO runs data collection and quality, and does not dispatch aid. No
individual case management is in the pilot. An optional case-management module is
deferred (`DOM-090`).

## Conventions

- **IDs** are stable from this revision on. Revision 3 renumbered the earlier draft
  IDs. Do not reuse a retired ID.
- **Priority:**
  - **P0:** pilot launch.
  - **P1:** during the pilot.
  - **P2:** later or optional.
- **Accept:** lines are checkable acceptance criteria. Every P0 requirement needs an
  automated test, or a documented manual check where automation is impractical.

## Pilot context

- **Operating NGO:** [Ciudadanía Sin Límites](https://ciudadaniasinlimites.org/about/)
  (CSL), metropolitan Caracas. CSL's [Monitor Ciudad](https://www.monitorciudad.com)
  project is an external evidence source, mocked until a feed is available
  (`DAW-030`).
- **Resident-facing identity:** "Metron Reporter". CSL is named in the notice as the
  organization responsible for the data.
- **Multi-NGO by design:** each operating NGO is a tenant with its own areas, providers,
  campaigns, and **privacy profile**. CSL uses the `protective` profile.
- **Need categories:** `water_drinking`, `water_other`, `charging`. **Service
  observations:** `electricity`, `piped_water`.
- **Geography:** data-driven areas (state → municipality → parish → sector, plus
  aliases). Development seeds synthetic Libertador parishes. The real sector list is
  configuration.
- **Stack (D19):** Python backend (FastAPI, SQLAlchemy/Alembic, PostgreSQL/PostGIS), and
  a React/TypeScript web app.
- **WhatsApp:** Meta Cloud API. The account, number, templates, and production adapter
  belong to a separate contributor. This repo owns the interface, the fake adapter, and
  the conversation logic.
- **Connectivity:** online-only, built for low bandwidth.
- **Scale assumptions** (validate before load testing):
  - Up to 5,000 reports per day normally, and a 10× surge for an hour after a regional
    blackout ends.
  - Up to 50 provider organizations, about 25 operating-NGO staff, and public dashboard
    traffic in the low thousands of views per day.

## Users and roles

### Personas

| Persona | Needs |
|---|---|
| Resident reporter | Report an outage or need quickly; hear about help available nearby; stop messages at any time. |
| Intake volunteer | Enter reports for neighbors without connectivity, quickly, on a phone. |
| Data coordinator (operating NGO) | Run campaigns, manage areas and meeting points, vet providers, watch coverage and data quality. |
| Reviewer (operating NGO) | Resolve duplicates, conflicts, floods, and unresolved locations, so aggregates stay trustworthy. |
| Provider | See where need is greatest and least served, log their own activity, get alerts, export or pull data, and (if vetted) reach residents who opted in. |
| Analyst | Trends and coverage across time and areas. |
| Public viewer | A coarse, safe public picture of conditions (if the operating NGO enables it). |
| Org administrator | Users, providers, privacy profile, policies, revocation, audit. |

### Roles

Roles are scoped to one operating-NGO tenant. A user may hold several roles.

| Role | Can see | Can do |
|---|---|---|
| `org_admin` | Everything the privacy profile stores. Contact details are masked by default and unmasked with an audited reason. | Users, provider vetting, privacy profile, policies, revocation, audit |
| `coordinator` | Reports, aggregates, provider activity, data quality | Campaigns, areas, meeting points, broadcasts, provider scopes |
| `reviewer` | Reports and observations in review tasks | Data-quality dispositions, merges, area corrections |
| `intake_volunteer` | Only reports they entered, for 72 hours | Assisted intake |
| `provider` | Aggregates and provider activity. If **vetted**, also the opt-in contact list within its scope. | Log activity, alerts, aggregate export, API keys, a contact-list export if vetted |
| `analyst` | Aggregates only | Reports and aggregate exports |
| *(public)* | The public dashboard only, if enabled | — |

A provider user belongs to a `provider_organization` inside the operating NGO's
tenant, with:

- vetting status: `unvetted` / `vetted` / `suspended`
- scope: areas × categories
- a responsible contact and a data-handling statement version

Cross-tenant views that aggregate several operating NGOs are P2 (`DOM-095`).

## Privacy profiles

Each operating NGO chooses a **privacy profile**. The platform enforces it everywhere:
intake questions, storage, views, exports, retention, and the API.

| Setting | `protective` (CSL default) | `standard` |
|---|---|---|
| Names | Not asked, not stored | Optional, stored encrypted |
| Location kept | Sector + chosen **meeting point** (`punto de encuentro`) | Sector + exact address/landmark (encrypted); optional GPS point |
| Reporter phone | Kept only while the reporter consents to follow-ups; deleted 7 days after the last activity when they have not | Kept per the retention policy |
| Household records | None (report-centric; repeat reports are linked by a short-lived pseudonymous key) | Pseudonymous household records allowed |
| Opt-in contact list fields | Alias, sector, meeting point, phone | Name, address, phone |
| Public dashboard | Off by default; parish level, k ≥ 10, at least 24 hours of delay | Allowed; sector level, k ≥ 5 |

Rules for changing profiles:

- A profile is a versioned org policy, and the privacy notice version follows it.
- **Tightening** (standard → protective) runs a purge job over existing data and is
  audited.
- **Loosening** applies only to reports collected after the change, under the new
  notice. It is never applied to data already held.
- Settings can be adjusted individually within platform minimums (for example, k ≥ 3
  everywhere).

**Meeting points** are public places per sector, such as a plaza, church, school, or
bodega, managed by coordinators. In the protective profile, residents pick the nearest
meeting point instead of giving an address. Providers who contact residents arrange to
meet there.

## Threat model and security

The platform supports a **hostile-state** operating environment (CSL's case). The
protective profile is designed for it. These requirements apply in every profile.

**Risks considered:**

1. Seizure of staff, volunteer, or provider devices.
2. Demands on operating-NGO staff or providers to hand over data.
3. Traffic interception or metadata analysis.
4. Malicious or compromised provider accounts, or API keys, harvesting data.
5. Bot infiltration, or flooding with false reports.
6. Re-identification from aggregates or the public dashboard, or targeting of areas.

**Security requirements:**

- **SEC-01 Minimization (P0).** Never collect political affiliation, identity documents,
  photos of people, health diagnoses, or household rosters. Collect names and addresses
  only when the profile allows it.
- **SEC-02 Anonymous area reports (P0).** Anyone can report area conditions with no
  personal record.
- **SEC-03 Location handling (P0).**
  - Aggregates use areas only. No aggregate, public view, or API returns points or
    addresses.
  - Precise locations (standard profile) are encrypted and restricted.
- **SEC-04 Hosting (P0).** Data, backups, and keys are hosted outside Venezuela. Field
  encryption keys are held in a managed key or secret service.
- **SEC-05 Authentication (P0).**
  - Google OAuth, or email + password with mandatory TOTP.
  - Server-side sessions in `HttpOnly` cookies, with a 30-minute idle timeout and a
    12-hour absolute limit.
  - API keys for providers are separate, scoped, and revocable (`API-063`).
- **SEC-06 Revocation (P0).** Revoking a user, a provider organization, or an API key
  takes effect within 1 minute. Users can revoke their own sessions.
- **SEC-07 No sensitive device storage (P0).** No personal data in persistent browser
  storage. Sensitive responses are `no-store`.
- **SEC-08 Least-privilege views (P0).** Contacts are masked by default. Provider views
  show only what their role and vetting allow.
- **SEC-09 Export and API control (P0).**
  - Aggregate exports and API responses are small-cell-suppressed.
  - Contact-list exports are vetted-only, consent-bound, scoped, watermarked,
    expiring, rate-limited, and audited.
- **SEC-10 Small-cell suppression (P0).** Suppress or merge cells under *k* distinct
  reporters or households. *k* is set per profile, with a platform minimum of 3.
- **SEC-11 Abuse resistance (P0).** Rate limits, flood and coordinated-report detection
  routed to review, and outlier flags on aggregates.
- **SEC-12 Neutral identity (P0).** Per-campaign display identity; CSL uses "Metron
  Reporter".
- **SEC-13 Audit (P0).** Append-only audit, with no raw personal data, of:
  - detail reads and unmasking
  - every export and API key use (aggregated per key per day)
  - vetting, scope, and profile changes
  - merges
  - broadcasts
  - retention actions
- **SEC-14 Runbook (P0, non-technical).** Procedures for data demands, device loss,
  breach, and provider or API-key compromise. The platform supports revocation, key
  rotation, access queries, and scoped purge.
- **SEC-15 Scoped emergency purge (P1).** With two-admin approval, purge contacts and
  location details for an area or campaign. Aggregates are kept.
- **SEC-16 Consent-bound contact (P0).** Each of these is a separate, withdrawable
  permission:
  - refresh prompts
  - area information broadcasts
  - inclusion on the provider contact list

  Withdrawal takes effect immediately for future use.
- **SEC-17 Public dashboard safety (P0).** The public dashboard is coarser than the
  provider view, by area level, *k*, and time delay as set in the profile.
  - It never shows contact data, provider contact-list data, or report free text.
  - Can be disabled instantly by an org admin.

## Cross-cutting non-functional requirements

- **NFR-01 Language (P0).** Resident-facing text is in Spanish (Venezuelan). The staff,
  provider, and public UI is Spanish-first, with English available. Strings are
  externalized.
- **NFR-02 Time (P0).** Stored in UTC and shown in `America/Caracas`. The precision of
  observation times is preserved.
- **NFR-03 Low bandwidth (P0).**
  - Usable on 3G.
  - Initial load ≤ 300 KB compressed JS+CSS.
  - The public dashboard's first view loads in ≤ 3 s, with no map tiles until the map
    is opened.
- **NFR-04 Devices (P0).** Android 9+ Chrome at a 360 px width, and current desktop
  browsers. WCAG 2.1 AA.
- **NFR-05 Availability (P0).** 99.5% monthly for intake and the API. Accepted reports
  are never lost.
- **NFR-06 Responsiveness (P0).**
  - p95 read ≤ 500 ms; webhook acknowledgment ≤ 2 s; bot reply ≤ 10 s.
  - Aggregates reflect a confirmed report within 5 minutes.
- **NFR-07 Surge (P0).** Absorb a 10× surge for one hour without loss. Lag is visible.
  A holding message is sent when lag exceeds 2 minutes.
- **NFR-08 Recovery (P0).** Recovery point objective ≤ 1 hour; recovery time objective
  ≤ 8 hours. Restore is tested before launch and quarterly.
- **NFR-09 Retention (P0, per profile; defaults).**
  - Raw message content: 30 days.
  - Reporter phone: per profile.
  - Precise location (standard profile): 90 days after the last report.
  - Report detail: 18 months, then anonymized.
  - Audit: 3 years.
  - Aggregates: indefinitely.
  - Export files: 24 hours.
- **NFR-10 Observability (P0).** Redacted logs, correlation IDs, and alerts on lag,
  failures, stuck conversations, and aggregate staleness.
- **NFR-11 Synthetic development (P0).** Only synthetic data and the fake WhatsApp
  adapter outside production.

## Pilot success measures

Targets are set with CSL after a baseline week.

- Reports per day and per parish; intake completion and abandonment.
- Area coverage: share of pilot sectors with a report in the last 24 hours, or with
  fresh external data.
- Indicator freshness, and the share of reports still pending review.
- Provider engagement: active providers per week, logins, exports, API calls, and alert
  subscriptions.
- **Coverage gaps:** areas with high need and no logged provider activity, and how long
  they stay uncovered.
- Refresh-prompt response rate, and the share of needs reported resolved by residents.

## Decisions

| # | Decision | Outcome |
|---|---|---|
| D1 | Who fulfills | Providers, with their own resources. The platform aggregates and informs. |
| D2 | Resident-facing identity | "Metron Reporter" |
| D3/D4 | Charging and water operations | Out of scope. Needs recorded as `water_drinking`, `water_other`, `charging`. |
| D5 | Areas | Data-driven, seeded with synthetic Libertador parishes |
| D6 | Staff identity | Google OAuth, with email + password + TOTP as backup |
| D7 | WhatsApp | Meta Cloud API, built by a separate contributor |
| D8 | Urgent reports | Immediate referral information, plus coordinator review. No dispatch promise. |
| D12 | Retention | Defaults accepted, now set per profile (NFR-09) |
| D19 | Backend stack | Python: FastAPI, SQLAlchemy/Alembic, PostgreSQL job tables |
| D20 | Product purpose | **Data aggregation platform.** Case management is deferred (`DOM-090`). |
| D21 | Household data | **Per-NGO privacy profile.** `protective` (meeting points, no names) or `standard` (names and addresses). CSL uses protective. |
| D22 | Provider capabilities | Dashboards and map, activity logging, area alerts, export and API access, public dashboard, and an opt-in contact list for vetted providers |
| D23 | Reporter follow-up | Refresh prompts plus area information broadcasts, each with its own permission |

### Still open

| # | Decision | Status |
|---|---|---|
| D10 | Real Monitor Ciudad schema and terms | P2 |
| D11 | Basemap provider | Before map launch |
| D13 | Voice notes | P1 |
| D14 | Object storage provider | Before data-worker deploy |
| D15 | Urgent referral content | **Launch blocker** |
| D16 | Provider vetting criteria and data-handling statement | **Launch blocker** |
| D18 | WhatsApp integration agreement (webhook hosting, templates, secrets) | **Launch blocker** |
| D24 | Whether CSL enables the public dashboard, and at what granularity and delay | **Launch blocker** |
| D25 | The pilot sectors' meeting-point lists | **Launch blocker** |
| D26 | Alert delivery channel for providers (email only, or also WhatsApp) | P0 decision |
