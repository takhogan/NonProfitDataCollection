# Database and persistence

PostgreSQL with PostGIS is the proposed persistence layer. This component will own
versioned migrations, transaction/repository implementations, indexes, access
policies, and synthetic seeds. No executable migrations exist yet.

Implement the logical model from [PLATFORM_PLAN.md](../../PLATFORM_PLAN.md) in stages:

1. Organizations/memberships; households/contacts; assessments/observations; cases/needs.
2. Resources/allocations; water runs/deliveries; charging sites/slots/bookings/sessions.
3. Invitations/conversations/messages; inbox/outbox/jobs; permissions and audit history.
4. Review/evidence, aggregate read models, and later sharing/referrals.

Audit fields, organization ownership, and permission enforcement belong in the
first stage even when their richer UI arrives later. Any live contact collection
requires the relevant permission records; synthetic fixtures do not authorize it.

Use organization-scoped foreign keys, server authorization, and row access policies.
Application roles must not bypass tenant isolation. Workers must set transaction-local
organization context explicitly. Separate sensitive contacts/locations from aggregate
read models, and avoid personal information in logs or audit summaries.

Enforce units, positive fulfillment quantities, valid time intervals, provider event
uniqueness, and operation idempotency. Implement stock/slot reservation transactionally.
Do not hold a database transaction open while calling WhatsApp.

First deliverable: repeatable local migrations and synthetic fixtures for two
organizations, including a negative cross-organization access test.
