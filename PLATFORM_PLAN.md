# Venezuela power and water needs data platform

Planning draft · 7 November 2026 · revision 3: data aggregation platform

> **What this is.** This is a **data aggregation platform**, not an aid dispatch
> platform.
> - It collects reports of power and water outages and household needs.
> - It turns them into area-level indicators of need.
> - It lets **providers** (NGOs, water distributors, charging hosts, relief groups)
>   log in, see which areas need help, and act with their own resources.
>
> The first operating NGO is [Ciudadanía Sin Límites](https://ciudadaniasinlimites.org/about/)
> (CSL), in metropolitan Caracas. Residents see the service as **Metron Reporter**.
> Each operating NGO chooses a privacy profile: `protective` (CSL's choice, with no
> names or addresses and nearby meeting points instead) or `standard`.
>
> Sections on per-household case management and NGO-run fulfillment are kept as
> **deferred design**. Requirements, roles, privacy profiles, and decisions are in
> [components/REQUIREMENTS.md](components/REQUIREMENTS.md). Where they differ from this
> plan, the requirements win.

## Product goal and scope

Show, area by area and as current as possible, where people lack electricity, piped
water, drinking water, or the ability to charge devices. The platform also shows how
many people are affected, how urgently, how reliable the information is, and which
areas no provider is serving yet. Providers use this to decide where to act, and log
what they are doing so others can coordinate around them.

The platform is a reporting and aggregation system with an outage intelligence layer.
It does not decide who receives aid. It does not treat neighborhood consensus or
external data as proof that anyone does or does not need help.

Data collected:

- **Service observations:** `electricity` and `piped_water` status, with when they were
  observed.
- **Needs:** `water_drinking`, `water_other`, and `charging`, with people affected,
  remaining supply, urgency, and access notes.
- **Provider activity:** who is doing what, where, and when.
- **External context:** Monitor Ciudad (mocked until a feed exists), and satellite night
  lights later.

Pilot assumptions to validate:

- a small set of Caracas sectors
- Spanish-first intake
- volunteers supporting people with limited connectivity
- a set of providers willing to log their activity

No field research or provider integration has been performed for this draft.

## End-to-end workflow

1. **Set up a campaign.** The operating NGO chooses areas, intake questions, its privacy
   profile, meeting points per sector, staffed hours, and urgent referral content.
   Areas follow state → municipality → parish → sector, with local aliases.
2. **Invite reporting.** Volunteers share a WhatsApp entry link with an opaque campaign
   token. A forwarded link identifies the campaign, not a person.
3. **Explain and ask.** The bot identifies itself and the responsible NGO. It explains
   that reports show organizations where help is needed, that it does not deliver aid,
   and that reporting does not guarantee help.
4. **Collect a short report.** Who is reporting (self, household, community), the
   sector, a location by profile (meeting point or address), electricity and water
   status with times, needs, and urgency. Unknown answers, correction, and pause/resume
   are allowed.
5. **Ask permissions separately.** Refresh prompts, area information broadcasts, and
   inclusion on vetted providers' contact list are each optional.
6. **Confirm.** The reporter confirms a short Spanish summary. Only confirmed reports
   count.
7. **Aggregate.** Reports update area indicators within minutes:
   - need and status mix, people affected, urgency, freshness
   - coverage (reported, thin, or unknown)
   - a confidence label with reasons

   Small cells are suppressed.
8. **Quality review.** Reviewers handle duplicates, comparable conflicts, unresolved
   locations, floods, and outliers. Disagreement never removes a report. Only a human
   duplicate or spam disposition does.
9. **Providers act.** Providers see:
   - areas of greatest need, ranked by declared criteria
   - a need map and a coverage view of uncovered high-need areas
   - alerts and exports, and API access

   They log their activity so coverage updates for everyone. Vetted providers may see
   reporters who opted in to be contacted.
10. **Keep data fresh.** With permission, the bot asks reporters every few days whether
    the problem continues. With separate permission, coordinators can broadcast
    provider activity in their area (for example, a water point opening). Needs go
    stale and then expire if nobody confirms them.
11. **Publish safely (optional).** A delayed, coarse public dashboard shows conditions
    and public provider activity.

## Suggested first bot conversation

- "Hola, somos Metron Reporter. Recogemos reportes sobre cortes de luz y agua para mostrar a organizaciones dónde se necesita ayuda. No entregamos ayuda directamente y reportar no garantiza ayuda. Los datos los gestiona Ciudadanía Sin Límites. Puedes pedir hablar con una persona."
- "¿Reportas por tu hogar, por otra persona o por tu comunidad?"
- "¿En qué sector estás?"
  - Protective profile: then "¿Cuál de estos puntos de encuentro te queda más cerca?"
    (list, plus "ninguno cerca").
  - Standard profile: "¿Dirección o referencia?"
- "¿Cómo está la electricidad ahora? Disponible / Sin servicio / Intermitente / No sé."
- "¿Cómo está el agua por tubería ahora? Disponible / Sin servicio / Intermitente / No sé."
- For each affected service: "¿Desde cuándo? ¿Cuándo lo comprobaste por última vez?"
  Approximate times are accepted.
- "¿Tu hogar tiene agua para beber? Sí / Poca / No / No sé."
- "¿Qué necesitan? Agua para beber / Agua para otros usos / Cargar equipos." Then
  "¿Para cuántas personas?" or "¿Cuántos equipos?"
- "¿Hay una necesidad urgente?"
  - A "yes" sends the agreed emergency and referral contacts immediately, and queues
    coordinator review.
  - There is no dispatch promise.
- Three separate permission questions:
  - "¿Podemos escribirte cada pocos días para saber si sigue el problema?"
  - "¿Quieres recibir avisos de ayuda disponible en tu zona?"
  - "¿Aceptas que organizaciones verificadas que ayudan en tu zona vean tu número para
    contactarte?"
- Confirm the summary. Explain that the report helps show where help is needed. Mention
  `ACTUALIZAR`, `DÓNDE`, `PERMISOS`, and `BAJA`.

Keep the path short. Do not require photos, identity documents, GPS, rosters, or
diagnoses. The bot is not an emergency service.

## Need-specific questions

Water: whether the water is for drinking or other use, people to serve, remaining
supply, whether they have containers, and preferred times. Do not ask the reporter to
estimate liters, though they may give a number. The platform never infers that water
is safe to drink.

Charging: device types and counts, whether they have a charger or cable, whether they
can reach a charging point, and preferred times.

*Deferred fulfillment design:* the coordinator workflows for water delivery runs and
charging-site slots are kept in the schema section below as reference for `DOM-090`.

## Provider-facing views

- **Areas of need:** a ranked table by declared criteria (urgent active needs, active
  needs per reporter, age of oldest unmet need, freshness). The method version is
  shown. There are no hidden weights.
- **Need map:** a choropleth by sector or parish and category. Unknown areas are hatched
  and suppressed areas are marked. No points are drawn.
- **Coverage:** `covered`/`uncovered`/`unknown` per area × category, from provider
  activity. Covered means someone is acting, not that needs are met.
- **Area detail:** trends, service status, provider activity, external context, and
  data quality.
- **Activity log, alerts, exports, API keys**, and for vetted providers, the opt-in
  contact list (fields per privacy profile).

Never add liters, people, devices, reporters, and households into one total. Every
number states its unit, time bucket, freshness, coverage, and confidence.

## Operating-NGO console

**Coverage and data health:** sectors with no recent reports, stale indicators, the
review backlog, uncovered high-need areas, unconfirmed provider activities, and intake
volume. This tells the NGO where to send outreach and volunteers.

**Report browser:** masked report detail for coordinators and reviewers. There are no
household profiles or cases in the pilot.

**Review queue:** duplicates, comparable conflicts, uncertain locations, floods,
outliers, and urgent flags. Reviewers see the evidence, the rule reasons, and the
effect on aggregates.

**Providers:** vetting, scope, activity oversight, sharing history, and API key usage.

**Privacy profile and public dashboard settings:** with a preview of consequences.

**Analytics:**

- report volume and intake completion
- coverage and freshness by sector
- provider engagement (logins, activities, exports, API use)
- time areas stay uncovered
- refresh response rates

Always separate reports, distinct reporters, households (standard profile), estimated
people, and needs. Submissions are not a representative estimate of the population
without a sampling design.

## Cross-checking without mistaking disagreement for fraud

Compare individual claims, not whole people. Every observation needs a service, subject scope, location, observation time, source, and uncertainty.

Examples:

- Household A has no power; household B nearby has power at the same time. This suggests localized variation or different connections. Keep both observations; do not mark either household dishonest.
- The same household reports no power at 10:00 and restoration at 15:00. This is a service transition, not a contradiction.
- Two independent observers describe the same water distribution point as both available and unavailable at overlapping times. This merits clarification about timing, access, and meaning of “available.”
- Several forwarded messages repeat one original account. They are several messages but not necessarily independent evidence.
- Piped water is restored, but a household has no safe drinking water. The service observation and unmet need are different facts.

Proposed review pipeline:

1. Normalize service vocabulary, location precision, time zone, approximate observation intervals, and firsthand versus secondhand source.
2. Detect replayed messages and potential duplicate submissions separately from contradictory reports.
3. Compare only sufficiently compatible service, subject scope, geography, and time intervals. Geographic proximity generates candidates; it does not prove the households share infrastructure. Support optional service zones when reliable boundaries become available.
4. Store explicit links: supports, potentially conflicts, supersedes, or possible duplicate. Preserve comparison-rule version and reasons.
5. Request a short follow-up or route to a reviewer. Field checks and external operational sources can add evidence but are not assumed infallible.
6. Record a reasoned disposition, evidence references, reviewer, and expiration/review date. New evidence can reopen review.

Keep **evidence assessment** separate from **need urgency** and **assistance decision**. Start with transparent labels such as unreviewed, corroborated, disputed, and unresolved, plus specific reasons. Do not launch a numerical “truth score” without calibration against reviewed outcomes. No automatic denial based solely on disagreement, reporting frequency, a shared phone, or missing evidence.

## Logical data schema

This is a logical schema, not an executable migration. IDs are UUIDs unless noted. Operational records carry `organization_id`, `created_at`, `updated_at`, and applicable retention metadata. Timestamps are stored as UTC instants; preserve the reported local time zone and time precision. `?` indicates an optional field. Foreign-key names refer to the corresponding entity's `id`.

### Organizations and outreach

```text
organization(id, name, status)
user(id, auth_subject)
organization_membership(id, organization_id, user_id, role, status)
campaign(id, organization_id, name, starts_at, ends_at?, status,
         questionnaire_version_id)
campaign_area(id, organization_id, campaign_id, area_id)
outreach_invite(id, organization_id, campaign_id, volunteer_membership_id?,
                token_hash, contact_endpoint_id?, channel, sent_at?, expires_at?)
```

Roles: org administrator, coordinator, reviewer, intake volunteer, provider, and analyst, plus a public read-only view. See the [roles table](components/REQUIREMENTS.md#roles). Volunteers see only the reports they entered. Invitations can be reusable campaign links or individually issued links; neither proves identity.

### Contacts, households, and permissions

The person, household, and location-history records below apply only in the `standard`
privacy profile, or with the deferred case-management module. In the `protective`
profile, reports link to a rotating pseudonymous `reporter_key` instead, and location
is a sector plus a meeting point.

```text
privacy_profile_version(id, organization_id, version, settings_json,
                        notice_version, activated_by_membership_id, activated_at)
reporter_key(id, organization_id, endpoint_hmac, epoch, created_at, expires_at)
meeting_point(id, organization_id, area_id, name, kind, public_description,
              public_point?, status)
person(id, organization_id, preferred_name?, preferred_language?)
household(id, organization_id, reference_code, estimated_member_count?,
          current_location_id?)
household_member(id, organization_id, household_id, person_id,
                 relationship?, valid_from, valid_to?)
contact_endpoint(id, organization_id, channel, encrypted_address,
                 address_lookup_hmac, status)
person_contact(id, organization_id, person_id, contact_endpoint_id,
               relationship, is_safe_to_contact, valid_from, valid_to?)
permission_record(id, organization_id, person_id?, contact_endpoint_id?,
                  purpose, notice_version, processing_basis?, decision,
                  captured_at, expires_at?, withdrawn_at?, evidence_reference?)
household_location_history(id, organization_id, household_id, location_id,
                           valid_from, valid_to?)
```

Do not require individual records for all household members; an estimated household count can be enough. Many people can share one endpoint. Lookup HMACs use protected keys and are organization scoped; never use a plain phone-number hash or expose a global contact lookup across NGOs. Optional sharing permission is not blanket permission for all future organizations. The operating NGO must establish the appropriate processing basis locally; do not assume consent is the only applicable basis.

### Geography and outage episodes

```text
area(id, parent_area_id?, type, name, official_code?, boundary?, source?, version?)
location(id, organization_id, area_id?, encrypted_description?,
         restricted_point?, accuracy_meters?, precision, source)
service_zone(id, organization_id, service_type, name, boundary?, source?, version?)
outage_episode(id, organization_id, service_type, area_id?, service_zone_id?,
               started_at?, ended_at?, status, assessment_basis)
```

Public administrative boundaries can be shared reference data. Household points and landmarks are sensitive. A report can exist without a confirmed outage episode; clustering can be corrected later. Do not force a precise point from an ambiguous place name.

### Intake and observations

```text
questionnaire_version(id, organization_id, version, language, definition_json)
conversation(id, organization_id, contact_endpoint_id, campaign_id?,
             active_questionnaire_version_id, intake_state, last_user_message_at,
             assigned_membership_id?)
message(id, organization_id, conversation_id, channel_account_id,
        provider_message_id, direction, content_reference?, sent_at?, received_at?,
        delivery_status, retention_until)
assessment(id, organization_id, conversation_id?, source_message_id?,
           questionnaire_version_id, reporter_person_id?, household_id?,
           campaign_id?, source_channel, reporting_relationship,
           answers_json, submitted_at, confirmed_at?, supersedes_assessment_id?)
observation(id, organization_id, assessment_id, household_id?, location_id,
            service_zone_id?, outage_episode_id?, service_type, subject_scope,
            status, observation_start_at?, observation_end_at?, time_precision,
            reported_timezone, outage_started_at?, onset_precision?,
            source_kind, source_group_id?, supersedes_observation_id?)
evidence(id, organization_id, observation_id, kind, restricted_object_reference?,
         external_source_url?, captured_at?, received_at, retention_until)
```

Suggested `service_type`: electricity, piped_water. Suggested observation `status`: available, unavailable, intermittent, unknown. Drinking-water reserves belong to the household assessment/need, not to the piped-water status field. Preserve original answers; normalize operational fields for searching. A source group records known common provenance, not a speculative identity judgment.

One assessment can contain several observations and several needs. `source_channel` supports WhatsApp, phone, and volunteer-assisted intake from the start. An observation's time interval expresses uncertainty about when it was observed; it is distinct from the estimated outage onset.

### Needs, indicators, and providers (pilot)

In the pilot, `assessment` above is called a **report**. It carries
`privacy_profile_version_id` and `reporter_key_id`, and in the standard profile an
optional `household_id`.

```text
need(id, organization_id, assessment_id, category, people_affected?,
     quantity?, unit?, remaining_supply, stated_urgency, access_notes?,
     preferred_times?, status, last_confirmed_at, supersedes_need_id?)
indicator_cell(id, organization_id, area_id, level, subject, bucket, bucket_start,
               active_needs, distinct_reporters, distinct_households?,
               people_known, people_unknown_count, urgency_mix, supply_mix,
               status_mix, freshness_at, coverage_label, confidence_label,
               confidence_reasons, suppressed, method_version,
               profile_version_id, input_watermark)
coverage_cell(id, organization_id, area_id, category, coverage, activity_ids,
              computed_at)
provider_organization(id, organization_id, name, vetting_status, scope_json,
                      responsible_contact_reference, statement_version,
                      may_disclose_name)
activity(id, organization_id, provider_organization_id, type, category,
         schedule_json, capacity?, public_location_ref?, visibility, status,
         last_confirmed_at)
activity_area(id, organization_id, activity_id, area_id)
alert_subscription(id, organization_id, membership_id, area_ids, category,
                   trigger, threshold?, channel, muted)
api_key(id, organization_id, membership_id, key_hash, scopes, expires_at,
        last_used_at?, revoked_at?)
share_event(id, organization_id, provider_organization_id, actor_ref,
            reporter_key_id, fields_shared, export_record_id?, occurred_at)
broadcast(id, organization_id, activity_id, template, approved_by_membership_id,
          recipient_count, sent_at?)
public_indicator_cell(...)  -- delayed, coarse snapshot (DOM-080)
```

- `need.status` is `active`, `stale`, `resolved_by_reporter`, `withdrawn`, or
  `expired`. No assignment or closure workflow exists in the pilot.
- `subject` is a need category or a service type.
- Indicator and coverage cells are derived and recomputed, never edited by hand.
- The contact list is a derived view: reporters with list consent and an active need
  in a vetted provider's scope. Each view or export writes `share_event` rows in the
  same transaction.
- Needs may remain after service restoration.

### Deferred: case management (DOM-090)

```text
case_record(id, organization_id, household_id, campaign_id?, status,
            assigned_membership_id?, opened_at, closed_at?, closure_reason?)
case_assessment(id, organization_id, case_id, assessment_id)
case_event(id, organization_id, case_id, event_type, actor_membership_id?,
           occurred_at, details_json)
```

### Deferred: NGO-run fulfillment

The records below apply only if an operating NGO or provider later manages fulfillment inside this
platform. They are kept here as a design reference.

```text
assistance_decision(id, organization_id, need_id, decision, rationale,
                    policy_version, decided_by_membership_id, decided_at,
                    supersedes_decision_id?)
resource_offer(id, organization_id, category, unit, available_quantity,
               availability_start, availability_end?, area_id?)
allocation(id, organization_id, need_id, resource_offer_id, quantity, unit,
           status, allocated_by_membership_id, allocated_at)
delivery(id, organization_id, allocation_id, quantity, unit, status,
         dispatched_at?, delivered_at?, recorded_by_membership_id,
         recipient_confirmed_at?, feedback?, failure_reason?)
```

Water needs need units and a time period: “20 liters today” differs from “20 liters daily.” A case can include multiple outage episodes through its assessments. Model partial deliveries explicitly. Do not mark a need fulfilled merely because resources were allocated or dispatched. Count distributor-reported and recipient-confirmed deliveries separately.

### Water and charging extensions

`water_need_detail`, `charging_need_detail`, and `charging_device_request` are **pilot**
records. They hold the need details shown to providers. The remaining extensions
(supply, runs, stops, sites, slots, bookings, sessions) are **deferred** with the
fulfillment records above.

Keep common case/need/allocation records, with typed service details. If fulfillment is reinstated, `delivery` records physical water deliveries; charging fulfillment uses `charging_session`. Every extension inherits organization ownership and enforced organization-scoped foreign keys.

```text
water_need_detail(need_id PK/FK, intended_use, people_to_serve?,
                  remaining_supply_hours?, has_containers?,
                  container_capacity_liters?, receiving_assistance_needed?,
                  delivery_location_id, preferred_window_start?,
                  preferred_window_end?, quantity_estimation_basis?)
water_supply(resource_offer_id PK/FK, source_reference, intended_use,
             release_status, release_check_reference?, checked_at?)
delivery_run(id, organization_id, assigned_membership_id?, scheduled_start,
             scheduled_end?, capacity_liters, status)
delivery_stop(id, organization_id, delivery_run_id, allocation_id,
              location_id, stop_order, planned_liters, window_start?,
              window_end?, status)
water_delivery_detail(delivery_id PK/FK, delivery_stop_id,
                      supply_reference, exception_note?)
charging_need_detail(need_id PK/FK, can_reach_site?, access_assistance_needed?,
                     preferred_window_start?, preferred_window_end?)
charging_device_request(id, organization_id, need_id, device_type,
                        device_count, connector_type?, has_charger?)
charging_site(id, organization_id, location_id, name, operating_hours,
              timezone, supported_devices, supported_connectors,
              simultaneous_device_capacity, status, last_checked_at)
charging_slot(resource_offer_id PK/FK, charging_site_id,
              starts_at, ends_at, device_capacity, status)
charging_booking(id, organization_id, allocation_id, device_request_id,
                 reserved_device_count, status, checked_in_at?,
                 replaces_booking_id?)
charging_session(id, organization_id, charging_booking_id,
                 started_at, ended_at?, devices_served, outcome,
                 recipient_confirmed_at?, interruption_reason?)
```

In this deferred design, water needs (`water_drinking`/`water_other`) are fulfilled in liters and `charging` in device sessions. A charging slot's resource offer uses device sessions and exactly the same availability interval. A device session means one device using one configured slot, not a guaranteed full battery. A booking references its slot through its allocation's resource offer; reject references to any other offer type. A water delivery references its reserved supply through its allocation. Enforce matching need categories, resource types, units, and allocation ownership across these references.

Require one service detail record matching each need category. Sum charging device requests to derive requested sessions for the relevant period; do not count the same device request twice when rebooking. A session interrupted before useful service leaves follow-up outstanding; staff record whether further charging is needed. A household case closes only when all needs have an explicit resolved, withdrawn, or otherwise reviewed disposition.

If charging fulfillment is reinstated, use non-overlapping slots per charging site. Atomically check active reservations against slot device capacity, and validate capacity against site limits. A walk-in receives a booking before using remaining capacity. Cancellation releases only unused reserved capacity; completed usage remains consumed for that slot. Longer sessions require an explicit extension into available capacity. Prevent open sessions from silently overlapping subsequent bookings beyond the site's simultaneous limit.

Water allocations cannot exceed released supply; delivery-run planned loads cannot exceed run capacity. Actual delivery quantities are positive and cannot exceed remaining allocation without a recorded adjustment. Apply unique fulfillment operation IDs so an offline retry cannot double-count water delivered or charging sessions. Record staff-reported completion separately from recipient confirmation in both workflows.

### Verification, deduplication, and governance

```text
observation_link(id, organization_id, observation_a_id, observation_b_id,
                 relation, rule_version, reasons_json, created_by_membership_id?)
review_task(id, organization_id, observation_id?, case_id?, reason,
            status, assigned_membership_id?, due_at?, resolved_at?)
review_decision(id, organization_id, review_task_id, disposition, rationale,
                reviewer_membership_id, decided_at, review_after?)
review_evidence(id, organization_id, review_decision_id, evidence_id)
duplicate_candidate(id, organization_id, entity_type, entity_a_id, entity_b_id,
                    match_reasons, status, reviewed_by_membership_id?)
merge_event(id, organization_id, entity_type, source_id, destination_id,
            approved_by_membership_id, occurred_at, reversal_reference?)
audit_event(id, organization_id, actor_id?, action, entity_type, entity_id,
            occurred_at, request_id, redacted_change_summary)
```

For review tasks, require at least one target; enforce typed entity references in implementation rather than trusting unchecked generic IDs. Merges require human approval and reversible provenance. Audit records should not duplicate raw messages, phone numbers, or precise coordinates.

### Later: collaboration between organizations

```text
sharing_agreement(id, owner_organization_id, recipient_organization_id,
                  purpose, permitted_fields, starts_at, expires_at, revoked_at?)
case_referral(id, sharing_agreement_id, source_case_id, recipient_case_id?,
              status, requested_at, accepted_at?, responsibility_note)
sharing_access_event(id, sharing_agreement_id, actor_id, resource_reference,
                     accessed_at, purpose)
```

Start with aggregate coverage sharing and explicit referrals. Keep original records owned by the originating NGO. Cross-organization access requires an active scoped agreement and explicit authorization; an ordinary organization foreign key must never grant access. Receiving a referral should explicitly establish who owns follow-up. Defer global beneficiary matching until governance, safe matching methods, and correction procedures are established.

## Database invariants and implementation choices

- Prefer a relational database with spatial support, such as PostgreSQL with PostGIS, for report, area, and indicator relationships and geographic queries. This is an architecture proposal, not a verified deployment stack or version selection.
- Use organization-scoped composite foreign keys or equivalent enforced constraints on operational relationships, plus row-level access controls and API authorization. A client-supplied organization ID is not authorization.
- Enforce unique inbound provider message IDs per channel account. Use separate deduplicated delivery-status events; delivery updates can arrive more than once or out of order.
- Retain assessment and observation revisions. Never overwrite the historical fact that an earlier report was made; controlled deletion/anonymization for retention still applies.
- Validate nonnegative quantities, matching units, valid time ranges, recognized statuses, and valid relationship scope. Prevent self-links and duplicate observation-pair relations.
- Read provider contact-list exports from a consistent snapshot, and record their share events in the
  same transaction.
- If fulfillment is reinstated, lock or transact resource reservations so simultaneous
  coordinators cannot allocate the same remaining stock.
- Index organization + observation time + service, organization + area + need status, indicator cells by area/subject/bucket, provider message identifiers, and spatial fields. Indicator and coverage cells are derived from source tables and can be rebuilt, never a second untraceable set of facts.
- Store media separately with restricted access and expiry. Encrypt contact details and sensitive location data; manage keys separately. Restrict and audit exports as well as on-screen access.

## Technical shape

```text
Volunteer invitation → Resident sends WhatsApp message
    → authenticated webhook → durable inbox/queue
    → resumable intake workflow → normalized assessments and observations
    → confirmed reports + comparison rules + data-quality review
    → area indicators, coverage, and alerts (suppressed)
    → provider portal / API / optional public dashboard
    → provider activity logs → coverage; refresh prompts and area broadcasts
```

Use a modular application with two distinct worker components: a Python operational worker (same codebase as the FastAPI API) for intake, messaging, and domain commands, and a separate Python data worker for external-source ingestion and geospatial evidence processing. The operational worker claims jobs from application-owned PostgreSQL tables with `FOR UPDATE SKIP LOCKED`. The data worker claims its own data jobs through a versioned internal API with leases, retries, and idempotent completion, and never reads the job tables or changes aid decisions directly. See [component boundaries](components/README.md) and the [data-job contract](components/contracts/data-jobs.md). Acknowledge webhooks after durable acceptance; retry processing safely, quarantine failures, and allow operators to replay failed jobs. Store outbound messages in a transactional outbox to avoid losing acknowledgements and follow-ups. Monitor failures, queue lag, message delivery, and stuck conversations.

A deterministic conversation flow is sufficient for the pilot. Optional AI can transcribe, translate, or propose structured fields; retain provenance and confirmation. AI should not invent locations, decide that an outage claim is false, or exclude reports from aggregates.

Power and connectivity disruptions also affect reporting. Include telephone/volunteer-assisted entry and resumable conversations. Record when conditions were observed separately from when delayed messages arrived. Design a field-friendly low-bandwidth interface; full offline synchronization can follow after the pilot establishes the need.

## Messaging and data handling constraints

WhatsApp's current Business Messaging Policy requires permission for proactive contact, approved templates for initiating Platform conversations, and approved templates outside the 24-hour window following a user's last message. It also requires clear escalation options for automation. Build opt-out handling and human handoff into the first release. A volunteer sharing a link does not authorize unrestricted automated follow-ups. See [WhatsApp Business Messaging Policy](https://business.whatsapp.com/policy).

Adopt an NGO-approved data-sharing and retention policy before live collection. OCHA describes responsible humanitarian data management as safe, ethical, and effective handling of personal and non-personal data, and identifies information-sharing protocols as a key operational mechanism. See [OCHA Centre for Humanitarian Data](https://centre.humdata.org/data-responsibility/).

Proposed product safeguards: avoid collecting political affiliation or identity documents; restrict exact locations; share aggregate patterns by default; suppress or combine small groups in shared analytics; give people correction and complaint routes; and define deletion across records, media, exports, and backup expiry. Permission withdrawal should stop optional future outreach and trigger the applicable handling process, rather than promising instantaneous erasure of every lawful operational record. Local privacy, hosting, and cross-border requirements remain to be assessed with the NGO; this document makes no jurisdiction-specific legal conclusions.

## Delivery plan and pilot acceptance

**Stage 1 — operational design.** Interview CSL coordinators, volunteers, prospective
providers, and residents.
- Agree on sectors, meeting points, the privacy profile, urgent referral content,
  provider vetting, whether to enable the public dashboard, and success measures.
- Test the Spanish wording, including whether residents distinguish piped-water
  availability from drinking-water need.
- Ask providers which views, alerts, and exports they would actually use.

**Stage 2 — reporting.** Implement assisted intake, the WhatsApp bot with
profile-dependent location and permissions, campaign attribution, and webhook ingestion.

Gates:
- A report can be completed, resumed after interruption, and corrected.
- A replayed webhook creates no duplicate.
- Protective mode stores no name, address, or GPS.

**Stage 3 — aggregation and provider portal.** Implement indicator cells, suppression,
coverage and confidence labels, the areas-of-need ranking, the need map, provider
accounts and vetting, activity logging, coverage, alerts, exports, and API keys.

Gates:
- A confirmed report appears in indicators within 5 minutes.
- Repeat reports from one reporter count once.
- Unknown areas are never shown as zero.
- Small cells are suppressed in every view, export, API response, and alert.
- An activity changes coverage immediately.
- Unvetted providers never see contact data.

**Stage 4 — quality, freshness, and external context.** Implement comparison rules and
the review queue, outlier and flood detection, refresh prompts and need expiry, area
broadcasts, the mock Monitor Ciudad pipeline, and the optional public dashboard.

Gates:
- Nearby disagreement never removes a report.
- Different-time restoration is a transition, not a conflict.
- Expired needs leave indicators.
- The public dashboard is coarser and delayed, and turns off instantly.

**Stage 5 — bounded live pilot.** Launch in agreed sectors with named staff and a manual
fallback. Review reporting volume, coverage, freshness, provider engagement, how long
areas stay uncovered, and who the channel excludes.

Security gates:
- One organization cannot read another's records, including exports, API keys, and
  background jobs.
- A provider cannot read beyond its role and vetting.
- Tightening a profile purges disallowed fields.

Set quantitative targets with CSL after a baseline week.

**Stage 6 — multiple organizations.** Onboard further operating NGOs with their own
profiles. Consider cross-tenant aggregates under sharing agreements (`DOM-095`) and the
optional case-management module (`DOM-090`) only when governance justifies them.

Decisions made and still open are tracked in the
[requirements decisions table](components/REQUIREMENTS.md#decisions). Open launch
blockers:

- urgent referral content
- provider vetting criteria and data-handling statement
- the WhatsApp integration agreement
- whether and how CSL enables the public dashboard
- the pilot sectors' meeting points
