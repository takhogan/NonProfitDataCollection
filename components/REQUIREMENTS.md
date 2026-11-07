# Platform requirements

Requirements draft · 7 November 2026 (decisions D1–D12 recorded the same day)

This document holds the context shared by every component: the pilot, users, roles,
threat model, cross-cutting non-functional requirements, and decisions. Each
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

The data-meaning rules in [PLATFORM_PLAN.md](../PLATFORM_PLAN.md) still apply. For example:

- A phone is not a person.
- Unknown is not zero.
- Restoration does not close a need.
- Disagreement never denies help.

**Where this file and the plan differ, this file wins.** In particular, the plan
assumes the NGO delivers water and charging. The pilot decisions below make CSL an
**intake, communication, and information-sharing** service, and partners do the
delivering. Architecture and stack choices stay in each component's `README.md`.

## Conventions

- **IDs** are stable (`WEB-012`). Do not reuse a retired ID; mark it *withdrawn* or
  *deferred*.
- **Priority:**
  - **P0:** required for the pilot to launch.
  - **P1:** expected during the pilot.
  - **P2:** later, or only if the scope changes.
- **Accept:** lines are checkable acceptance criteria. Each P0 requirement needs an
  automated test, or a documented manual check where automation is impractical.
- Cross-references use IDs. For example, `DOM-020` is enforced by `DB-031`.

## Pilot context

- **Operating NGO:** [Ciudadanía Sin Límites](https://ciudadaniasinlimites.org/about/)
  (CSL), a Venezuelan human-rights and democracy organization. Its related project
  [Monitor Ciudad](https://www.monitorciudad.com) crowdsources water and electricity
  service reports through 300+ volunteer informants in metropolitan Caracas.
- **Resident-facing identity:** the bot and campaign are presented as
  **Metron Reporter**. CSL is named in the privacy notice as the data controller.
- **What CSL does:**
  - listens to affected residents through WhatsApp and assisted intake
  - records outages and needs (water and charging)
  - triages them
  - keeps residents informed
  - shares the information with partner organizations through the dashboard and
    controlled exports
- **What CSL does not do in the pilot:** deliver water, run charging sites, manage
  stock, or schedule deliveries. Partners do that with their own tools. Partners *may*
  report outcomes back in the app, but the platform must work without that data.
- **Water needs:** both drinking water and water for other household use are recorded,
  and the two are kept separate. **Charging needs:** devices, and whether the resident
  can reach a site. Both are recorded so partners can act on them; neither is fulfilled
  by the platform.
- **Geography:** metropolitan Caracas. Areas are fully data-driven (state →
  municipality → parish → sector + aliases). Development seeds a few Libertador
  parishes with synthetic data, for example Sucre, 23 de Enero, and Santa Rosalía. The
  real sector list is loaded later as configuration, not code.
- **Pilot MVP (P0):**
  - assisted intake and WhatsApp bot intake
  - the household/case CRM
  - triage
  - partner sharing (dashboard + export)
  - the evidence review queue
  - the Python data worker with a **mock Monitor Ciudad source**
  - the aggregate area map
- **Monitor Ciudad:** there is no access to its live feed, so the data worker uses a mock
  source that follows an assumed schema (`DAW-030`).
- **WhatsApp:** the production Meta Cloud API adapter, the Meta Business account, the
  number, and the templates are **built and owned by a separate contributor**. This repo
  owns the adapter *interface*, the normalized contracts, the fake adapter, and the
  conversation logic (`WA-001`).
- **Connectivity:** field use is online-only and built for low bandwidth. There is no
  offline sync. A paper/phone fallback is documented (`WEB-090`).
- **Scale assumptions** (validate before load testing):
  - Up to 2,000 households and about 25 CSL staff and volunteers.
  - Up to 15 partner organizations with 1–5 users each.
  - 5,000 inbound WhatsApp messages per normal day. After a regional blackout ends,
    a surge of 10× that rate over one hour.

## Users and roles

### Personas

| Persona | Context | Primary needs |
|---|---|---|
| Resident | Caracas household. Intermittent power and data; often a shared or prepaid phone; Spanish; may send voice notes. | Report a problem quickly, know whether anyone can help, get a human, correct or withdraw. |
| Intake volunteer | CSL volunteer or Monitor Ciudad informant helping neighbors by phone or in person. | Fast assisted intake on a phone, minimal personal data on screen. |
| Caseworker | CSL staff who owns cases and talks to residents. | Queue of cases, household history, next action, messaging the household. |
| Coordinator | CSL operations lead. | Backlog and urgency by area, what has been shared with which partner, reassign work. |
| Reviewer | CSL staff with data/GIS background. | Resolve conflicts, duplicates, uncertain locations with evidence visible. |
| Partner | Staff of a water, charging, or relief organization, on a phone or laptop. | See where needs are, download a contact list of people who agreed to be contacted, and optionally say who they helped. |
| Analyst | CSL researcher. | Aggregate area trends and coverage; never household records. |
| Org administrator | CSL lead. | Users, partners, campaigns, policies, exports, emergency revocation. |

### Roles

Roles are permissions inside CSL's organization tenant. A user may hold several roles.

| Role | Can see | Can do |
|---|---|---|
| `org_admin` | Everything except raw contacts by default (it can unmask contacts with an audited reason) | Manage users, roles, and partners; vet partners; campaigns; policies; revocation |
| `coordinator` | All cases, queues, sharing history | Assign, triage, mark needs shareable or not, manage partner scopes |
| `caseworker` | Assigned cases plus unassigned queue summaries | Intake, update needs, message household, record dispositions |
| `reviewer` | Review tasks with linked observations and evidence | Dispositions, merge proposals, link observations |
| `intake_volunteer` | Only the intakes they created, for 72 hours | Assisted intake |
| `partner` | Aggregate dashboard and map (small cells suppressed). If **vetted**, also the contactable list inside its scope. | Export aggregates; if vetted, export the contactable list; optionally report outcomes on listed needs |
| `analyst` | Aggregate read models only | Aggregate reports and exports |

**Partners** are members of CSL's tenant with the `partner` role and a
`partner_organization` attribute, not separate tenants. A partner organization has:

- **Vetting status:** `unvetted` (aggregate only) or `vetted`. Only `org_admin` can vet.
- **Scope:** the parishes or sectors it serves, and the need categories it handles
  (`water_drinking`, `water_other`, `charging`).
- A named **responsible contact**, plus an agreed data-handling statement on file.

A vetted partner sees and exports only the **contactable list**. That list contains
only the households that meet all of the following:

- they gave explicit sharing consent for this purpose (`DOM-070`)
- they are in the partner's scope
- they have an open, triaged need that CSL marked shareable

Partners never see review data, household history, observations from other areas, or
anyone without sharing consent. The P2 cross-tenant sharing agreements in
PLATFORM_PLAN.md remain the long-term model.

## Threat model and security posture

CSL's human-rights and democracy work means the platform assumes a **hostile-state
adversary**.

**Adversaries and risks considered:**

1. Seizure or coerced unlock of a staff, volunteer, or partner device.
2. Legal or extra-legal demands on CSL staff or partners in Venezuela to hand over data.
3. Interception or metadata analysis of traffic inside Venezuela.
4. A malicious or compromised insider or **partner** account harvesting household data.
   Partner exports are the largest planned outflow of personal data.
5. Infiltration of the bot to map who is reporting, or flooding it with false reports.
6. Dashboards or exports that allow re-identification.

**Security requirements:**

- **SEC-01 Data minimization (P0).**
  - Never collect political affiliation, cédula or other identity documents, photos of
    people, health diagnoses, or household rosters.
  - Names are optional. A household is identified by a random reference code.
- **SEC-02 Anonymous area reports (P0).** A resident can report area conditions with no
  household or person record. Their number is kept only for the messaging window, then
  discarded (NFR-09).
- **SEC-03 Location coarsening (P0).**
  - The default stored location is the area plus an encrypted landmark description.
  - Precise coordinates are optional, encrypted, restricted, and auto-discarded.
  - Aggregate views never show points.
- **SEC-04 Hosting and keys outside Venezuela (P0).**
  - Production data, backups, and keys are hosted outside Venezuela (proposed: US
    Virginia).
  - Field-encryption keys are kept in a managed key service separate from the database.
- **SEC-05 Authentication (P0).**
  - Primary sign-in is Google OAuth/OIDC. The backup is email + password, which
    **requires TOTP MFA**.
  - Passwords are hashed with Argon2id and checked against breached-password lists.
  - Lockout and reset flows do not reveal whether an account exists.
  - Idle timeout is 30 minutes and the absolute session limit is 12 hours.
  - Partners may use either method.
- **SEC-06 Rapid revocation (P0).**
  - An org admin can revoke any user's or partner organization's sessions, export
    links, and reveal tokens within 1 minute.
  - Any user can revoke their own sessions from another device.
- **SEC-07 Nothing sensitive at rest on devices (P0).** No household data in persistent
  browser storage. Sensitive responses are `no-store`. Caches clear on logout or
  timeout.
- **SEC-08 Least-privilege views (P0).** Phones are masked by default. Unmasking
  requires a reason and is audited. Partner list views show the minimum fields
  (`DOM-075`).
- **SEC-09 Export control (P0).**
  - Aggregate exports have small cells suppressed.
  - Contactable-list exports (vetted partners and CSL staff) contain only the minimum
    fields and only consented, in-scope households.
  - Each export is watermarked (a visible requester and timestamp, plus a per-export
    identifier embedded in the file).
  - Export links expire in 24 hours. Exports are rate-limited (default 10 per partner
    per day) and audited.
  - Any other household-level export by CSL staff requires `org_admin` approval with a
    purpose.
- **SEC-10 Small-cell suppression (P0).** Aggregates suppress or merge cells under *k*
  distinct households (default 5, minimum 3).
- **SEC-11 Bot abuse resistance (P0).** Rate limits, flood detection routed to review,
  and no disclosure of other residents' data or of staff or partner identities.
- **SEC-12 Neutral resident-facing identity (P0, decided).** Residents see
  **Metron Reporter**. CSL appears as data controller in the notice. Per-campaign
  display identity stays configurable.
- **SEC-13 Audit everything sensitive (P0).** Append-only audit, with no raw personal
  data, covering:
  - detail reads
  - unmasking
  - every export, with its row count and scope
  - partner vetting and scope changes
  - role changes
  - merges
  - retention actions
- **SEC-14 Runbook (P0, non-technical).**
  - CSL approves procedures for data demands, device loss, suspected breach, and a
    **partner incident** (lost export, compromised account).
  - The platform supports revocation, key rotation, a "what did user/partner X access
    or export" query, and a scoped purge.
- **SEC-15 Scoped emergency purge (P1).** With two-admin approval, irreversibly purge
  contact endpoints and precise locations for an area or campaign. Aggregates are kept.
- **SEC-16 Consent-bound sharing (P0).** Sharing consent is purpose-specific ("share my
  contact and need with organizations that can help").
  - Withdrawing consent removes the household from all future partner lists
    immediately.
  - The withdrawal is logged.
  - The bot tells residents that partners who already received earlier exports may
    still hold the data, and that CSL will ask them to delete it.

## Cross-cutting non-functional requirements

- **NFR-01 Language (P0).** Resident-facing text is Spanish (Venezuelan register). The
  staff and partner UI is Spanish-first, with English available. All strings are
  externalized.
- **NFR-02 Time (P0).** Stored in UTC and displayed in `America/Caracas`. The precision
  of observation times is preserved.
- **NFR-03 Low bandwidth (P0).**
  - Usable on 3G (≈400 kbps, 400 ms round-trip time).
  - The initial load is ≤ 300 KB of compressed JS+CSS.
  - Intake and partner list screens load in ≤ 3 s.
  - No map tiles load by default.
- **NFR-04 Devices (P0).** Android 9+ Chrome at a 360 px width; current desktop
  browsers. Staff screens meet WCAG 2.1 AA.
- **NFR-05 Availability (P0).** 99.5% monthly for the API and webhook. Accepted inbound
  messages are never lost.
- **NFR-06 Responsiveness (P0).**
  - 95th percentile (p95) read ≤ 500 ms; p95 mutation ≤ 1 s.
  - Webhook acknowledgment p95 ≤ 2 s.
  - Bot reply p95 ≤ 10 s under normal load.
  - An export of ≤ 2,000 rows completes in ≤ 30 s.
- **NFR-07 Surge (P0).** Absorb a 10× surge for one hour without losing messages. Lag
  is visible to staff. A holding message is sent when lag exceeds 2 minutes.
- **NFR-08 Recovery (P0).** Recovery point objective (RPO) ≤ 1 hour; recovery time
  objective (RTO) ≤ 8 hours. Restore is tested before launch and quarterly. Backups
  are encrypted and kept outside Venezuela.
- **NFR-09 Retention (P0, decided defaults).**
  - Raw message content: 30 days.
  - Contact endpoints for anonymous area reports: 7 days after the last message.
  - Precise coordinates: 30 days after need closure.
  - Closed cases: anonymized after 18 months.
  - Audit events: 3 years.
  - Aggregates: indefinitely.
  - Export files: 24 hours on the server.
- **NFR-10 Observability (P0).** Redacted structured logs, correlation IDs, alerts on
  lag, failures, and stuck conversations, and a staff status banner.
- **NFR-11 Synthetic-only development (P0).** Non-production uses synthetic data and the
  fake WhatsApp adapter.
- **NFR-12 Cost (assumption).** Modest managed tiers. The budget ceiling has not been
  agreed.

## Pilot success measures

Targets are set with CSL after a baseline week.

- Intake completion rate, the step where people abandon, and correction rate.
- Time from intake confirmation to first CSL action (median, p90).
- Share of residents who received at least one status update after their report.
- Needs shared with at least one partner within 48 hours, by area and category.
- Partner engagement: exports per partner, share of listed needs with a
  partner-reported outcome (expected to be incomplete).
- Resident-reported outcome from follow-ups ("¿Recibiste ayuda?").
- Area freshness (< 24 hours) per parish. Review queue age and disposition mix.

## Decisions

| # | Decision | Outcome | Affects |
|---|---|---|---|
| D1 | Who fulfills | **Partners.** CSL shares information through the dashboard and exports. Partner outcome reporting is optional, and the platform must not depend on it. | `DOM-075`–`079`, `WEB-060`–`065`, `API-040`–`046` |
| D2 | Resident-facing identity | **Metron Reporter**, with CSL named as controller in the notice | `WA-040`, `OPW-020`, SEC-12 |
| D3 | Charging operations | **Out of scope.** Partners run charging. CSL records charging needs only. | `DOM-042`, `DOM-090` |
| D4 | Water supply | **Drinking and other use**, recorded as separate need categories. CSL delivers nothing. | `DOM-030`, `DOM-040`, `DOM-041` |
| D5 | Pilot areas | **Data-driven areas, seeded with synthetic Libertador parishes**. The real sector list comes later as configuration. | `DB-060`, `DAW-030` |
| D6 | Staff identity | **Google OAuth, with email + password + TOTP as backup** | `API-010`, SEC-05 |
| D7 | WhatsApp | **Meta Cloud API direct**, built and operated by a separate contributor against this repo's interface | `WA-*` |
| D8 | Urgent reports | **Immediate referral information + staff review in staffed hours**. No promise of response. | `OPW-025`, `WEB-030` |
| D9 | Allocation policy | **Withdrawn.** Partners decide quantities. | — |
| D12 | Retention | **Defaults accepted** (NFR-09) | `DB-070`, `OPW-060` |

### Still open

| # | Decision | Affects | Status |
|---|---|---|---|
| D10 | Real Monitor Ciudad schema and sharing terms (mock until then) | `DAW-030`–`039` | P2 |
| D11 | Basemap/tile provider; whether any map is public | `WEB-050`, SEC-10 | Before map launch |
| D13 | Voice notes: staff playback/transcription or decline | `WA-020`, `OPW-022` | P1 |
| D14 | Object storage provider and region | `DAW-060`, `DB-080` | Before data worker deploy |
| D15 | Urgent referral content: emergency numbers and partner contacts the bot sends (D8) | `OPW-025` | **Launch blocker** |
| D16 | Partner vetting criteria and data-handling statement wording | `DOM-076`, SEC-09 | **Launch blocker** |
| D17 | Exact contactable-list fields per need category (phone? landmark?) | `DOM-075`, `CON-014` | **Launch blocker** |
| D18 | Interface handoff with the WhatsApp contributor: who owns templates, webhook hosting, and secrets | `WA-001`, `WA-062` | **Launch blocker** |
