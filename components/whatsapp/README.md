# WhatsApp adapter

Provider boundary for the WhatsApp Business Platform, with a fake local adapter.
Choose direct Meta integration or a provider during implementation after verifying
current setup requirements and documentation. No live integration exists yet.

## Responsibilities

- Verify inbound requests using provider-documented mechanisms.
- Normalize messages and status events while preserving provider/account identifiers.
- Submit supported reply/template messages and normalize send errors.
- Expose message-window and template metadata needed by outbound orchestration.
- Provide fake inbound events, outbound capture, duplicate events, and failure fixtures.

Intake questions and case creation belong in contracts/domain/worker, not this adapter.
The application must check permission and permitted message type before sending;
the adapter should reject unsupported operations. Provide clear handoff and opt-out
paths in the conversation flow.

Store credentials outside Git. Redact phone numbers and message content from routine
logs. Raw payload storage, if needed, is restricted and time-limited. Document provider
retry behavior and delivery guarantees before relying on them.

First deliverable: a fake adapter capable of completing the Spanish intake locally
without contacting real people.
