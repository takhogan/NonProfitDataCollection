# WhatsApp conversation engine

How "Metron Reporter" turns a resident's WhatsApp messages into report rows.
Requirements: [operational-worker/REQUIREMENTS.md](../../../../operational-worker/REQUIREMENTS.md)
(OPW-010..040).

## Flow

1. **Webhook** (`app/routers/webhooks.py`): checks the signature, stores the
   payload in `inbound_event`, and returns 200. It sends nothing.
2. **Worker** (`scripts/worker.py`, `inbound.py`), each cycle:
   - **Surge mode**: if the oldest waiting message is older than
     `SURGE_LAG_SECONDS`, each waiting conversation gets one holding reply.
   - **Routing**: every message and status in the payload is matched to an
     organization through `channel_account` (`phone_number_id` → org) and
     handled in a tenant transaction under the worker role, so RLS applies.
   - **Terminal state**: each event ends as `processed`, `ignored` (with a
     reason) or `failed` after 8 attempts. Processed payloads are reduced to
     counts, so no phone numbers or text stay in the inbox.
3. **Engine** (`engine.py`) runs the questionnaire state machine stored in
   `conversation.state_json`. Replies go into `outbox_message` in the same
   transaction as the state change.
4. **Persistence** (`persistence.py`): on "Confirmar" it writes `report`,
   `observation`, `need` (+ details), `report_location` (address profile only),
   `permission` and `review_task` rows.
5. **Sender** (`sender.py`) delivers `outbox_message` rows through the adapter:
   - **Gate**: no messages after BAJA except its confirmation. Free-form text
     only inside the 24-hour window; outside it, templates only.
   - **Rate**: a token bucket, with resident replies sent before anything else.
   - **No double sends**: a send that may have reached Meta (timeout after
     submission) is never resent. It is reconciled through
     `biz_opaque_callback_data` on the status webhook, or marked
     `failed / uncertain_unconfirmed`.

## Questionnaire

The steps run in the order of `STEPS` in `engine.py`:

1. **Notice** (OPW-011): introduces Metron Reporter and the responsible
   organization, says it does not deliver aid and that reporting does not
   guarantee help, and offers a person. The acknowledgement is stored as a
   `permission` row (`notice_ack`).
2. **Area** (OPW-013):
   - parish, then sector, chosen from a list, by number, or by typed name or
     alias;
   - ambiguous input offers up to 3 candidates;
   - unresolvable input is kept as an encrypted note plus a review task.
3. **Location**, depending on the privacy profile:
   - protective: nearest meeting point or "Ninguno cerca". A shared GPS point
     is reduced to the area and discarded;
   - standard: an address or landmark (encrypted), or a shared location.
4. **Services**: electricity and piped water, each with "since when".
5. **Needs**: drinking water (people, liters, remaining supply), other water,
   charging (device type, count).
6. **Urgent** (OPW-021): a "yes" sends the referral text immediately and creates
   a review task.
7. **Permissions**: three separate yes/no questions (OPW-015). An unclear
   answer is recorded as "no".
8. **Summary**: "Confirmar" or "Corregir" (pick a section to redo, OPW-016).

How answers are handled at every step:

- "No sé" is accepted where it is offered.
- An unreadable answer is asked again once. The second time it is kept as an
  encrypted note, the report is flagged, and the bot moves on.
- The next question is always the first step without an answer. Prefilled
  answers, "Atrás" and corrections all follow from that rule.

**Global commands** (whole message, case- and accent-insensitive):

- AYUDA: hand off to a person; the bot stays quiet until MENÚ.
- BAJA: opt out; all permissions are withdrawn.
- MENÚ, ATRÁS
- CORREGIR: fix the last report, which is superseded.
- ACTUALIZAR: ask services and needs again; the new report supersedes the old
  one.
- DÓNDE: public activities in the resident's area.
- PERMISOS: review or toggle the three permissions.
- BORRAR: deletion request for staff.

**Media** (OPW-022): voice notes, images and files are not downloaded. The bot
explains this and repeats the question.

**Protective profile, repeat reports** (OPW-019): a new report supersedes the
reporter's latest one.

## OpenAI extraction (optional)

This is off unless `OPENAI_EXTRACTION=true` and `OPENAI_API_KEY` are set
(`extraction.py`, amended OPW-023).

**When it is used:** only when a typed answer can't be read by `parsing.py`, and
only at a step that allows it. Area, service and need steps allow it. Notice,
address, permission and summary steps never do.

**What is sent:** the question and the answer, redacted (phone numbers, e-mails,
links, ID numbers removed; capped at 280 characters).

**What comes back:** JSON in a strict schema (Structured Outputs).
`extraction.validate` drops wrong types, enum values and out-of-range numbers.
The engine applies the field for the current question and prefills other
unanswered questions; the resident still confirms them in the summary.

**Area names** the model returns are matched against the organization's own
area list. The model never sees ids and never writes SQL. Any OpenAI error
falls back to asking the question again.

## Setup

- Link the number: `python -m scripts.link_channel --phone-number-id <id> --org "<name>"`.
- Production needs `KMS_KEY_NAME` and `WRAPPED_DATA_KEY` (Cloud KMS envelope encryption; `deploy/gcloud-deploy.sh kms`).
- Demo: `WHATSAPP_FALLBACK_ORG_NAME` routes unlinked numbers to one organization.
- Tests: `tests/whatsapp/` (end-to-end on PostgreSQL with RLS, plus unit tests).

## Not done yet

- **OPW-019 household choice**: in the standard profile with household
  records, the bot does not yet ask which household a repeat report is for.
- **OPW-024 abuse detection**: no per-contact or per-area spike tasks yet.
- **OPW-003 ordering across replicas**: events are processed in received order
  by one worker (`min-instances=1`). Running several workers needs a
  per-conversation lock.
- **BORRAR and AYUDA** only set the conversation state (`deletion` / `handoff`).
  There is no staff screen for them yet.
- **Business-initiated sends** (refresh prompts, broadcasts) are not scheduled
  yet. The sender already supports templates for them.
