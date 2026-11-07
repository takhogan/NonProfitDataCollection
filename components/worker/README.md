# Background worker

Process durable jobs independently from HTTP requests while sharing domain rules.

## Responsibilities

- Normalize accepted inbound messages and advance resumable conversation state.
- Serialize conversation updates so concurrent messages do not corrupt intake.
- Submit outbound messages from the transactional outbox.
- Apply provider delivery updates without regressing status on older events.
- Retry transient failures with bounded backoff and expose terminal failures for staff.
- Later: reminders, observation comparisons, freshness updates, retention, and exports.

Start with a PostgreSQL-backed durable job/inbox/outbox implementation or an
established compatible library; choose the implementation during workspace setup.
Use leases, attempt counts, operation IDs, and explicit organization context.
Do not claim exactly-once network delivery: handle uncertain send outcomes using
provider capabilities and reconciliation rather than blindly resending.

Keep core assistance decisions synchronous and transactional in domain commands.
Worker crashes must not lose accepted messages or duplicate fulfillment.

First deliverable: consume a synthetic inbox event and produce a durable outbound
intent, including restart/retry verification.
