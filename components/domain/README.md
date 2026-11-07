# Domain logic

Shared application behavior used by the API and worker.

## Modules

- **Intake:** confirmed assessment creation, corrections, household linkage, and provenance.
- **Cases and needs:** assignments, urgency reasons, separate need states, and closure rules.
- **Water:** supply compatibility, reservations, partial deliveries, and outstanding quantities.
- **Charging:** site/slot compatibility, capacity reservation, sessions, and interruption follow-up.
- **Review:** comparable claims, explicit supporting/conflicting links, and human dispositions.
- **Permissions:** allowed contact purposes and optional sharing scope.

Commands include `submitAssessment`, `assignCase`, `allocateWater`,
`recordWaterDelivery`, `bookCharging`, `recordChargingSession`, and
`resolveReview`. Each receives actor/organization context and explicit inputs.

Enforce transaction-sensitive invariants using database constraints and locks through
repository interfaces, not only in-memory checks. Domain state transitions and
audit/outbox intents commit atomically. Keep provider payloads and HTTP concerns out.

Never infer identity from a phone alone, convert geographic disagreement into an
automatic denial, equate a booking with completion, or close other unmet needs when
one service is fulfilled. Evaluate repeated requests within their requested period.

First deliverable: submit a household assessment and create a case with separate
water and charging needs without accidental duplicate active needs on replay.
