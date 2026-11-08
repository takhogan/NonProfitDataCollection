# Web application

React application with three surfaces: the provider portal (primary), the operating-NGO console, and an optional public dashboard. Mobile-friendly.

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

Deploy the static build to a Render Static Site. Run Vite locally. Use a restricted
API origin allowlist and an authenticated API session; configure production web/API
origins together. Runtime versions and package pins will be set during implementation.

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
