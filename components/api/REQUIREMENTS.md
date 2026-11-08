# API requirements

The FastAPI boundary for operating-NGO staff, providers, the public dashboard, WhatsApp
webhooks, and the Python data worker. Rules are in [domain](../domain/REQUIREMENTS.md).
Shared context: [../REQUIREMENTS.md](../REQUIREMENTS.md).

## General

- **API-001 (P0) Versioned REST.**
  - Staff and provider endpoints live under `/v1`, public endpoints under
    `/public/v1`, and internal endpoints under `/internal`.
  - Pydantic request and response models, never raw ORM rows.
- **API-002 (P0) Consistency.** Request IDs, the `CON-040` error envelope, cursor
  pagination, and bounded date and area filters.
- **API-003 (P0) Thin routers.** Routers authenticate, authorize, validate, and call
  domain functions. No business logic in routers.
- **API-004 (P0) Profile-aware responses.** Every response that can contain personal
  fields is filtered by the active privacy profile and the caller's role, before
  serialization.

## Authentication

- **API-010 (P0) Sign-in (D6).**
  - Google OIDC (authorization code + PKCE). Only invited, verified emails can sign in.
  - Email + password with mandatory TOTP: Argon2id, a breached-password check,
    lockout, and generic errors.
  - Server-side sessions in `HttpOnly`/`Secure`/`SameSite=Lax` cookies, with SEC-05
    timeouts.
  - Interim: the current JWT bearer login stays allowed for local development only.
- **API-011 (P0) Context.** `GET /v1/me` returns memberships, roles, provider
  organization, vetting status, and the active privacy profile summary.
- **API-012 (P0) Revocation.**
  - Revoke a user, suspend a provider organization, or revoke an API key, each within
    60 s.
  - `POST /v1/me/revoke-all` lets users end their own sessions.
- **API-013 (P0) CSRF/CORS.** CSRF tokens on cookie-authenticated mutations, and
  credentialed CORS only from the web origin. The public API is uncredentialed.
- **API-014 (P0) Dev fixture.** A development-only sign-in that refuses to run in
  production.

## Authorization

- **API-020 (P0) Server-side checks.** Role and scope are checked on every request.
  PostgreSQL row-level security (`DB-002`) is a second layer.
- **API-021 (P0) Provider scope.** Provider endpoints return aggregates and activity.
  Contact-list endpoints require `vetted` status and stay within scope. Anything else
  returns `not_found`.
- **API-022 (P0) Isolation tests.** Tests run across tenants, across providers, and
  across profiles. A protective-profile tenant must never return name, address, or GPS
  fields from any endpoint.

## Intake and reports (operating NGO)

- **API-030 (P0) Assisted intake.**
  - `POST /v1/reports` submits a confirmed report (idempotent).
  - `POST /v1/reports/drafts` saves a resumable draft.
- **API-031 (P0) Report browsing.**
  - Coordinators and reviewers list and filter reports by area, category, status,
    review state, and time.
  - Detail views are audited.
  - Personal fields are masked, and revealing one requires a reason.
- **API-032 (P0) Meeting points.** CRUD per sector (coordinator). Read access for the bot
  and intake.
- **API-033 (P0) Campaigns.**
  - Areas, questionnaire version, display identity, staffed hours, and urgent referral
    content (D15).
  - Revocable entry tokens.

## Indicators and dashboards

- **API-040 (P0) Area indicators.** `GET /v1/indicators?level=&category=&bucket=` returns
  indicator cells (`DOM-040`), suppressed, with coverage and confidence labels and the
  method version.
- **API-041 (P0) Areas of need.** `GET /v1/areas-of-need` returns the ranked list
  (`DOM-043`), with the ranking criteria included in the response.
- **API-042 (P0) Coverage.** `GET /v1/coverage` returns area × category coverage
  (`covered`/`uncovered`/`unknown`) with the contributing activities.
- **API-043 (P0) Area detail.** `GET /v1/areas/{id}` returns indicators over time, service
  status, active provider activity, external context, and data quality.
- **API-044 (P1) Trends.** Week-over-week series per area and category.
- **API-045 (P0) Operating-NGO metrics.** Intake volume and completion, freshness, the
  review backlog, provider engagement, and refresh response rates.

## Providers

- **API-050 (P0) Provider organizations (admin).** CRUD, scope, responsible contact,
  statement version, vet and suspend with a reason, and invitations for provider users.
- **API-051 (P0) Activity log.**
  - `POST/PATCH /v1/activities` create and update activities for the caller's
    organization.
  - `GET /v1/activities` lists the tenant's activities (`DOM-053`).
  - `POST /v1/activities/{id}/confirm` refreshes `last_confirmed`.
- **API-052 (P0) Alert subscriptions.** CRUD for the caller's subscriptions (`DOM-055`).
  `GET /v1/alerts` returns recent alerts.
- **API-053 (P0) Contact list (vetted).**
  - `GET /v1/contact-list?category=&area=` returns profile-dependent rows (`DOM-054`)
    and writes share events.
  - `POST /v1/contact-list/exports` creates a watermarked, single-use, 24-hour export,
    rate-limited per provider.
- **API-054 (P0) Sharing history.** The operating NGO can query who saw or exported which
  reporters, by reporter, provider, or time.

## Exports and provider API

- **API-060 (P0) Aggregate export.** CSV/XLSX of indicators, coverage, or activity for
  the current filter, suppressed, for analysts, providers, and staff.
- **API-061 (P0) Provider API.** The same aggregate endpoints (`API-040`–`API-044`,
  `API-051` read) are available with an API key in place of a cookie, for providers'
  own systems.
- **API-062 (P0) API documentation.** The OpenAPI document includes the provider API,
  with examples. An API page is served to providers.
- **API-063 (P0) API keys.**
  - Created per provider user. Only a hash is stored, and the key is shown once.
  - Scoped to read-only aggregates and activity, plus contact list only when the
    provider is vetted and the key was created with that scope.
  - Expiry ≤ 1 year, rate-limited, usage audited per day, and revocable (SEC-06).
- **API-064 (P1) Change feeds.** `GET /v1/indicators/changes?since=` lets providers sync
  incrementally.

## Public API

- **API-070 (P0) Public dashboard data.**
  - `GET /public/v1/indicators` and `GET /public/v1/activities` return only `DOM-080`
    and `DOM-081` data, when the profile enables the public dashboard. Otherwise they
    return 404.
  - Responses are cacheable (CDN), with no cookies and per-IP rate limits.
- **API-071 (P0) Kill switch.** An org admin disables public endpoints instantly. Caches
  are purged or carry a short TTL (≤ 5 minutes).

## Review

- **API-080 (P0) Review queue.** Tasks by reason, area, and age, with detail: linked
  reports, rule reasons, external context.
- **API-081 (P0) Dispositions.** Record `DOM-072` dispositions and merges, which are
  reversible.

## Administration

- **API-090 (P0) Users and roles.** Invite, assign roles, deactivate, list sessions, and
  reset TOTP (audited).
- **API-091 (P0) Privacy profile.** View the active profile. Propose and activate a new
  version (org admin, with a second admin's confirmation when loosening). Show the
  effect: fields purged on tightening, and the new notice version on loosening.
- **API-092 (P0) Policies.** Versions for refresh, expiry, the ranking method,
  suppression, alerts, broadcasts, and export limits.
- **API-093 (P0) Audit query.** Who accessed or exported what, by user, provider, API
  key, and time.
- **API-094 (P1) Emergency purge.** Two-admin approval (SEC-15).
- **API-095 (P0) Broadcasts.** A coordinator previews the recipients count (never the
  list), approves the template text, and sends an area broadcast (`DOM-063`).

## Webhooks and internal endpoints

- **API-100 (P0) WhatsApp webhook.**
  - Verify the signature on the raw bytes.
  - Map the account to an org from configuration.
  - Persist to the inbox with deduplication, and acknowledge within NFR-06.
  - Do no processing in the request.
- **API-101 (P0) Webhook resilience.** Duplicates are acknowledged without a new record.
  A bad signature returns 401. A database outage returns 5xx.
- **API-102 (P0) Data-job endpoints.**
  - Claim, heartbeat, complete, and fail per [data-jobs.md](../contracts/data-jobs.md).
  - Uses a scoped service credential, not a staff session or provider key.
- **API-103 (P0) Artifacts and geometry.** Job-scoped upload URLs, checksum
  verification, and area geometry for the job's scope only.

## Operations

- **API-110 (P0) Health.** Separate liveness and readiness endpoints.
- **API-111 (P0) Rate limits.** Limits per user, per IP for sign-in, public endpoints,
  and webhook, per API key, and per provider for exports.
- **API-112 (P0) Redacted logging.** No phone numbers, names, addresses, message text,
  or API keys in logs. A CI scan checks for seeded personal data.
- **API-113 (P0) Status.** `GET /v1/status` returns intake lag, worker heartbeat, data job
  lag, and indicator freshness.
