# Web application

React application with three surfaces: the provider portal (primary), the operating-NGO console, and an optional public dashboard. Mobile-friendly.

## Running locally

`npm run start:dev` at the repo root starts this app together with the backend, the
worker and the dashboard API (`-- --web=http` for the real API); see
[Running locally](../../README.md#running-locally). To run only the web app:

Needs Node 24 (`.nvmrc`; `nvm use`). Dependencies are pinned exactly with a
committed `package-lock.json`.

```bash
cd components/web
nvm use
npm ci
npm run dev        # http://localhost:5173, provider portal on synthetic mock data
```

| Command | What it does |
|---|---|
| `npm run build` | Type-check (`tsc -b`) and production build to `dist/` |
| `npm run typecheck` / `npm run lint` | Type-check / ESLint |
| `npm test` | Vitest + React Testing Library |
| `npm run test:e2e` | Playwright journeys, desktop and Android 360 px (first run: `npx playwright install chromium`) |
| `npm run size` | After a build: initial JS+CSS gzip budget (300 KB, NFR-03) and "no map library in the initial bundle" |

**Mock vs real API.** The app talks to the planned `/v1` API through the
`ApiClient` interface in `src/api/client.ts`. By default it uses
`MockApiClient` (`src/api/mock/`), an in-memory implementation with synthetic
Caracas data (four Libertador parishes, invented sectors with aliases, meeting
points, suppressed and no-data cells, provider activities). To use the FastAPI
backend instead, set one variable (for example in `.env.local`):

```bash
VITE_API_MODE=http VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

The request/response types in `src/api/schema.ts` are **hand-written** from
`CON-*` and `API-*` until the backend publishes its OpenAPI document; then
replace them with `openapi-typescript` output (instructions at the top of that
file). `GET /v1/status` (status banner) and `GET /v1/areas` (area picker) are
assumed endpoints that the API requirements do not list yet.

**Dev-only controls.** In `npm run dev` with the mock, a striped "DEV ONLY" bar at
the bottom switches role (provider vetted/unvetted, coordinator, reviewer, intake,
analyst, admin, multi-role), simulates intake lag or degraded services, and makes
the next save fail (to exercise WEB-005). It is excluded from production builds.

**Production hosting notes.** Serve with a strict CSP header (WEB-063), e.g.
`default-src 'self'; connect-src 'self' <api-origin>; img-src 'self' data:;
style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'`, and
`Referrer-Policy: no-referrer`. The app loads no third-party scripts or fonts.
`firebase.json` sets these headers (see [HOSTING.md](HOSTING.md)).

## Requirement status

| Req | Status | Notes |
|---|---|---|
| WEB-001 Sign-in and context | Partial | Org, provider (with vetting), and roles always shown; role-filtered nav. No sign-in screen yet (needs API-010). |
| WEB-002 Role home screens | Partial | Routing per role is done; only the provider home is built, other homes are placeholders. |
| WEB-003 Language, time, units | Done | Spanish default, English toggle (in memory), `America/Caracas` times with relative age, "aprox." helper, units everywhere. |
| WEB-004 Honest numbers | Done | Unit, bucket, freshness, coverage label, confidence with reasons (tap/keyboard via `<details>`); "Datos insuficientes" / "Sin datos", never 0. |
| WEB-005 Save feedback | Done | No optimistic success; failed saves keep input and retry with the same operation key. |
| WEB-006 Performance | Partial | Routes code-split; initial ≈124 KB gzip; size check script. No map yet, so the map-lazy-load part is untested. |
| WEB-007 Status banner | Done (mock) | Intake lag > 2 min, stale indicators, degraded services. Endpoint assumed. |
| WEB-010 Areas of need | Done | Ranked table with declared criteria and method version, category/period/level filters, unranked list. |
| WEB-011 Need map | Not started | Needs D11 (basemap) and MapLibre. |
| WEB-012 Coverage view | Partial | Table, "uncovered, high need" call to action, activities per cell. Map not started. |
| WEB-013 Area detail | Done (mock) | Needs and services per period, 7-day history, activities, meeting points, separate external context, quality notes. |
| WEB-014 Log activity | Done | All fields; meeting-point picker; prefill from coverage gaps; shows on coverage immediately. |
| WEB-015 My activities | Done | Pause/resume, end (with confirmation), edit capacity and visibility, one-tap "still active", 7-day unconfirmed highlight. Schedule editing not yet. |
| WEB-016 Alerts | Done (mock) | Create (area set × category × trigger), mute/unmute, delete, recent alerts. Delivery channel is D26. |
| WEB-017 Exports | Partial | Client-side CSV of the current view from already-suppressed data. XLSX and the server export (API-060) to come. |
| WEB-018/019 | Not started | API keys, contact list. |
| WEB-030–045, 050–052, 070 | Not started | Console, admin, public dashboard, paper fallback. |
| WEB-060 No persistent storage | Done | No storage APIs (ESLint rule), in-memory caches cleared on "Salir" and role change; e2e asserts storage stays empty. Idle-timeout clearing still to do. |
| WEB-061 Masking | Not started | |
| WEB-062 Quick exit | Partial | "Salir" clears caches; server logout and "revoke all sessions" need API-012. |
| WEB-063 No third-party scripts | Partial | None used; CSP must be set by the host (see above). |

## Initial screens

- Sign-in and organization/role context.
- Provider portal: areas of need, need map, coverage view, area detail, activity log,
  alerts, exports, API keys, and the opt-in contact list for vetted providers.
- Operating-NGO console: assisted intake, coverage and data health, report browser,
  review, meeting points, broadcasts, providers, privacy profile, and public dashboard
  settings.
- Public dashboard (optional): coarse, delayed area conditions and public provider
  activity.

Use shared in-app UI components; a separate design-system package is unnecessary
initially. Display Spanish intake content, explicit units, local times, and observation
freshness. Make failed saves visible and preserve entered data for retry. Do not
silently imply offline support until synchronization has been implemented.

Access all data through the API. Client-side role checks improve presentation but
are not authorization. Avoid showing precise locations in aggregate views.

First deliverable: assisted intake → household case → two open needs.

## Proposed tech stack

- TypeScript + React + Vite for a client-rendered staff application.
- React Router for navigation and TanStack Query for server-state caching and invalidation.
- React Hook Form for multi-step intake. API request and response types are generated
  from the backend's OpenAPI (`openapi-typescript`), and the server is the final
  validator.
- CSS Modules and accessible native controls initially; a small shared UI folder.
- MapLibre GL JS when aggregate mapping is introduced. A map library does not supply
  tiles or grant tile-service rights; select an appropriately licensed basemap separately.
- Vitest + React Testing Library for important UI behavior; Playwright for the main
  assisted-intake, areas-of-need, and activity-logging journeys.

**Hosting decision (Nov 2026): Firebase Hosting, not Render.** The site is
Firebase Hosting in GCP project `csl-metron-webhook` with the neutral site ID
`metron-reporter` (`firebase.json`, `.firebaserc`). Today it serves only the
static home and privacy pages in `static-site/` that the Meta app links to. The
React build moves to the same site later, with `/v1/**` rewritten to the Cloud Run
service `whatsapp-webhook` (`us-east4`) so the API's `__Host-sid` cookie is
same-site. That rewrite is planned, not enabled: Firebase forwards only a cookie
named `__session` to Cloud Run, which must be settled first. See
[HOSTING.md](HOSTING.md). Run Vite locally. Configure production web/API origins
together (`WEB_ORIGIN` on the API).

## Internal layout and data flow

Planned folders: `src/app` (routing/session), `src/features/areas`, `coverage`,
`activities`, `alerts`, `contact-list`, `intake`, `review`, `admin`, and `public`; `src/api` (typed client), `src/ui`
(shared controls), and `src/locales` (Spanish-first labels).

Forms send explicit command payloads and show the server-confirmed result. Reports,
exports, and profile changes must not be optimistically marked successful.
Include organization context in cache keys and clear sensitive caches on sign-out
or organization change. Use pagination and coarse-area map queries rather than
loading every report into the browser.

## Build sequence and verification

Build the application shell, assisted intake, areas of need and coverage, activity
logging, and then the map, alerts, API keys, and public dashboard, in that order.
Verify keyboard operation, Spanish text, narrow screens, save failures, stale
capacity errors, and cache separation between organizations. Keep unsent personal
information in memory initially; persistent browser storage needs a deliberate
retention and shared-device design.

References: [React TypeScript](https://react.dev/learn/typescript),
[Vite](https://vite.dev/guide/).
