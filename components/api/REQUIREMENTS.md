# API requirements

The authenticated HTTP boundary for CSL staff, partners, WhatsApp webhooks, and the
Python data worker. Business rules are in [domain](../domain/REQUIREMENTS.md). Shared
context and decisions: [../REQUIREMENTS.md](../REQUIREMENTS.md).

## General

- **API-001 (P0) Versioned REST.**
  - Endpoints live under `/v1`.
  - Request and response bodies are validated against
    [contracts](../contracts/REQUIREMENTS.md).
  - Responses are explicit DTOs, never raw rows.
- **API-002 (P0) Consistent behavior.**
  - Every request has an ID, and every error uses the CON-040 envelope.
  - List endpoints use cursor pagination.
  - Date and area filters are bounded.
- **API-003 (P0) Thin routes.** Routes authenticate, authorize, validate, and call an
  application service. Business logic in route handlers fails review.

## Authentication and session

- **API-010 (P0) Sign-in (D6).**
  - The primary method is Google OAuth/OIDC (authorization code + PKCE). Only verified
    emails matching an invited membership can sign in.
  - The backup method is email + password with mandatory TOTP enrollment at first
    sign-in:
    - passwords hashed with Argon2id
    - breached-password check
    - progressive lockout
    - generic error messages
  - Password reset uses a single-use, 30-minute emailed link, and still requires TOTP
    or an admin reset.
  - Sessions are stored server-side in `HttpOnly`, `Secure`, `SameSite=Lax` cookies,
    with SEC-05 timeouts.
- **API-011 (P0) Membership context.** `GET /v1/me` returns memberships, roles, partner
  organization, and vetting status.
- **API-012 (P0) Revocation.**
  - `POST /v1/admin/users/:id/revoke` and `POST /v1/admin/partners/:id/suspend` end
    sessions, export links, and reveal tokens within 60 s (SEC-06).
  - `POST /v1/me/revoke-all` lets users revoke their own sessions.
- **API-013 (P0) CSRF/CORS.**
  - Mutations require a CSRF token.
  - Credentialed CORS is allowed only from the web origin.
  - Redirect targets are validated.
- **API-014 (P0) Dev identity fixture.** A development-only sign-in that refuses to run
  in production. A CI test checks this.

## Authorization

- **API-020 (P0) Server-side checks.** Every read and mutation checks role and resource
  scope. RLS (`DB-002`/`DB-003`) is a second layer, not a substitute.
- **API-021 (P0) Partner scoping.**
  - Partner endpoints return only aggregates, and, for vetted partners, the
    contactable list filtered by `DOM-075` from the caller's partner organization.
  - Any request outside that scope returns `not_found`.
- **API-022 (P0) Cross-tenant and cross-partner tests.** Every endpoint is tested
  against other orgs' IDs, and partner endpoints against other partners' scopes.

## Households, intake, and cases (CSL staff)

- **API-030 (P0) Assisted intake.**
  - `POST /v1/assessments` submits a confirmed intake (idempotent).
  - `POST /v1/assessments/drafts` saves resumable drafts.
- **API-031 (P0) Household search.** Search by reference code, exact phone
  (server-side HMAC match), area, or name. Results show no contacts, and searches are
  audited.
- **API-032 (P0) Detail.** `GET /v1/households/:id` and `GET /v1/cases/:id` return the
  timeline, needs, sharing history, outcome facts, and review flags. Reads are audited.
- **API-033 (P0) Contact reveal.** `POST /v1/contacts/:id/reveal` requires a reason. It
  returns the number, or a `tel:`/`wa.me` action that expires in 5 minutes. It is
  audited and rate-limited.
- **API-034 (P0) Case operations.**
  - Assign or reassign, set urgency with reasons, and edit need details (version
    check).
  - Mark a need shareable or not, with a reason.
  - Record a resolution disposition, and add notes.
- **API-035 (P0) Queues.**
  - `GET /v1/queues/{new|urgent|unassigned|handoff|followup|stale|not_shareable}`
    supports filters by category, area, urgency, age, and assignee.
  - `not_shareable` lists needs with no sharing consent, which CSL must handle itself
    or ask for consent.
- **API-036 (P0) Handoff.** List conversations waiting for a human, claim one, reply
  within the window or with a template, and return it to the bot or close it.
- **API-037 (P0) Messaging a household.** Staff send a template or free-form message
  (within the window) through the outbound gate. Examples: a status update, a request
  for missing information, or asking for sharing consent.

## Partner sharing

- **API-040 (P0) Partner organizations (admin).**
  - CRUD for partner organizations: responsible contact, data-handling statement
    version, scope (areas × categories), flags (name may be told to residents).
  - Vet and suspend, each with a reason.
  - Invite partner users.
- **API-041 (P0) Partner dashboard data.** Partners receive the same aggregate endpoints
  as analysts (`API-060`, `API-061`), restricted to aggregate DTOs.
- **API-042 (P0) Contactable list.**
  - `GET /v1/partner/list?category=&area=` is for vetted partners only. It returns
    `PartnerListRow[]`, paginated.
  - Each page view records a share event (`DOM-077`).
- **API-043 (P0) Partner export.**
  - `POST /v1/partner/exports` creates a CSV or XLSX of the current list scope with a
    watermark and records share events atomically (`DB-034`).
  - It returns a single-use download link that expires in 24 hours.
  - Exports are rate-limited per partner (SEC-09).
- **API-044 (P1) Partner outcomes.**
  - `POST /v1/partner/needs/:ref/outcome` records `contacted`, `helped`,
    `could_not_reach`, or `not_able_to_help` (idempotent).
  - It is accepted only for needs previously shared with that partner.
- **API-045 (P0) Sharing history (CSL).** Query what was shared with which partner, when,
  and by whom, by household, partner, or time range.
- **API-046 (P1) Service directory.** CRUD for partner service points (CSL coordinators),
  and a read endpoint for the bot.

## Review and evidence

- **API-050 (P0) Review queue.** List review tasks by reason, area, and age. Detail
  includes linked observations, rule reasons, external indicators, and history.
- **API-051 (P0) Dispositions and merges.** Record dispositions; propose, approve
  (coordinator), and reverse merges.
- **API-052 (P1) Manual evidence entry.** Reviewers attach attributed evidence: a
  utility notice, field check, or phone verification.

## Dashboards, analytics, exports

- **API-060 (P0) Area conditions.** `GET /v1/dashboard/areas` returns
  `AreaConditionCell[]` per level, service, and time bucket, suppressed per SEC-10. It
  never returns points.
- **API-061 (P0) Need demand.** `GET /v1/dashboard/demand` returns `NeedDemandCell[]`
  per area and category (open needs, households, people when known, urgency mix),
  suppressed.
- **API-062 (P0) Operational metrics (CSL only).**
  - Time to first action (median and p90).
  - Share of needs shared within 48 hours.
  - Follow-up response rate.
  - Partner-reported and resident-reported outcome counts, kept separate.
  - Freshness by area.
- **API-063 (P0) Aggregate export.** Aggregate CSV for analysts, partners, and staff,
  with suppression. Any other household-level export by staff needs `org_admin`
  approval (SEC-09).
- **API-064 (P0) Audit query.** An org admin asks what a given user or partner accessed
  or exported in a time range (SEC-14).
- **API-065 (P0) System status.** `GET /v1/status` returns inbox/outbox lag, worker
  heartbeat, and data job lag for staff.

## Administration

- **API-070 (P0) Users and roles.** Invite users, assign roles, deactivate them, list
  sessions, and reset TOTP (admin, audited).
- **API-071 (P0) Campaigns.** Configure areas, questionnaire version, display identity
  (default "Metron Reporter"), staffed hours, and urgent referral content (D15). Issue
  opaque, revocable entry tokens.
- **API-072 (P0) Policies.** Version and activate triage, escalation, follow-up,
  expiry, retention, suppression k, and export limits.
- **API-073 (P1) Emergency purge.** Request and approve a purge with two admins
  (SEC-15).

## Webhooks and internal endpoints

- **API-080 (P0) WhatsApp webhook.**
  - The webhook hosts the endpoint and calls the adapter's `verifyWebhook` on the raw
    bytes.
  - It maps the channel account to an organization from configuration.
  - It inserts into the inbox with deduplication and acknowledges within NFR-06.
  - There is no intake processing in the request.
  - If the WhatsApp contributor hosts the webhook elsewhere instead (D18), this becomes
    an authenticated internal ingest endpoint with the same guarantees.
- **API-081 (P0) Webhook resilience.**
  - Duplicates are acknowledged without a new record.
  - A bad signature returns 401 and is counted.
  - A database outage returns 5xx, so the provider retries.
- **API-090 (P0) Data-job endpoints.**
  - Claim, heartbeat, complete, and fail per [data-jobs.md](../contracts/data-jobs.md).
  - Authenticated with a scoped service credential. Staff cookies are not accepted.
- **API-091 (P0) Artifact access.** Short-lived, job-scoped upload URLs, with checksum
  verification.
- **API-092 (P0) Area geometry.** The data worker can read only the area geometries in
  its job's scope.

## Operations

- **API-100 (P0) Health.** Separate liveness and readiness endpoints; readiness checks
  the database.
- **API-101 (P0) Rate limits.** Limits per user, per IP for sign-in and password reset,
  per contact for reveal, and per partner for exports. Webhooks and internal endpoints
  have separate budgets.
- **API-102 (P0) Redacted logging.** No phones, message text, landmarks, names, points,
  or export contents in logs. A CI test scans the logs for seeded personal data.

## Deferred

- **API-110 (P2) Fulfillment endpoints.** Allocations, runs/stops, deliveries, charging
  sites/slots/bookings/sessions, only if `DOM-090` is reinstated.
