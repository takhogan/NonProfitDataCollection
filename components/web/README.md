# Web application

Staff-facing React application; mobile-friendly for volunteers and delivery staff.

## Initial screens

- Staff login and authorized organization context.
- Operations queues: water, charging, urgent/unassigned, and human handoff.
- Household search and profile, contact relationships, assisted intake, and case history.
- Case detail with independently tracked observations, needs, allocations, and outcomes.
- Water supply, delivery runs, stops, partial deliveries, and confirmation.
- Charging site status, capacity/calendar, bookings, check-in, and session outcomes.
- Later: observation review and aggregate geographic dashboard.

Use shared in-app UI components; a separate design-system package is unnecessary
initially. Display Spanish intake content, explicit units, local times, and observation
freshness. Make failed saves visible and preserve entered data for retry. Do not
silently imply offline support until synchronization has been implemented.

Access all data through the API. Client-side role checks improve presentation but
are not authorization. Avoid showing precise locations in aggregate views.

First deliverable: assisted intake → household case → two open needs.
