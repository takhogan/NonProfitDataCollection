# Web application

React application for CSL staff, volunteers, and partner organizations; mobile-friendly.

## Initial screens

- Staff login and authorized organization context.
- Operations queues: new, urgent, unassigned, handoff, follow-up, stale, not shareable.
- Household search and profile, contact relationships, assisted intake, and case history.
- Case detail with independently tracked observations, needs, sharing history, and outcomes.
- Partner portal: demand map, contactable list, export, and optional outcome reporting.
- Aggregate area condition and need demand maps.
- Later: observation review and aggregate geographic dashboard.

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
- React Hook Form for multi-step intake; shared JSON Schema validation at submission.
- CSS Modules and accessible native controls initially; a small shared UI folder.
- MapLibre GL JS when aggregate mapping is introduced. A map library does not supply
  tiles or grant tile-service rights; select an appropriately licensed basemap separately.
- Vitest + React Testing Library for important UI behavior; Playwright for the main
  assisted-intake and partner-sharing journeys.

Deploy the static build to a Render Static Site. Run Vite locally. Use a restricted
API origin allowlist and an authenticated API session; configure production web/API
origins together. Runtime versions and package pins will be set during implementation.

## Internal layout and data flow

Planned folders: `src/app` (routing/session), `src/features/households`, `cases`,
`sharing`, `partner`, `review`, and `dashboard`; `src/api` (typed client), `src/ui`
(shared controls), and `src/locales` (Spanish-first labels).

Forms send explicit command payloads and show the server-confirmed result. Capacity
exports, shares, and dispositions must not be optimistically marked successful.
Include organization context in cache keys and clear sensitive caches on sign-out
or organization change. Use pagination and coarse-area map queries rather than
loading every household into the browser.

## Build sequence and verification

Build the application shell, assisted intake, case detail, queues, and partner portal
in that order. Add review and maps after the underlying data is usable.
Verify keyboard operation, Spanish text, narrow screens, save failures, stale
capacity errors, and cache separation between organizations. Keep unsent personal
information in memory initially; persistent browser storage needs a deliberate
retention and shared-device design.

References: [React TypeScript](https://react.dev/learn/typescript),
[Vite](https://vite.dev/guide/).
