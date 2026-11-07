# Venezuela power and water response platform

Planning draft · 7 November 2026 · scope revised after pilot decisions the same day

> **Pilot scope.** The operating NGO is [Ciudadanía Sin Límites](https://ciudadaniasinlimites.org/about/)
> (CSL), in metropolitan Caracas. Residents see the service as **Metron Reporter**.
> CSL collects reports, triages needs, communicates with residents, and **shares needs
> with partner organizations**. Partners deliver water and run charging, using their own
> tools. Sections of this plan about NGO-run fulfillment (stock, allocations, delivery
> runs, charging slots) are kept as **deferred design** for a possible later phase.
> Feature requirements, roles, the threat model, and decisions are in
> [components/REQUIREMENTS.md](components/REQUIREMENTS.md). Where they differ from this
> plan, the requirements win.

## Product goal and initial scope

Help one NGO hear from households affected by power and water interruptions, understand
what they need, triage those needs, and get them to partner organizations that can
help, while keeping residents informed and learning from them whether help arrived.
Design organization ownership into the database now. Enable controlled collaboration
between organizations later.

The product is a needs intake, communication, and information-sharing system with an
outage intelligence layer. It should not treat neighborhood consensus as proof that a
household deserves or does not deserve assistance.

Need scope:

- **Drinking water** and **water for other household use**, recorded as separate needs.
- **Charging access** (devices, and whether the person can reach a site).

A household can report any combination in one case. Each need has its own status,
sharing state, and outcome facts. CSL does not deliver, so a need is resolved by a
recorded CSL disposition. That disposition is informed by resident follow-ups and,
when available, partner-reported outcomes.

Pilot assumptions to validate:

- a small set of Caracas communities selected with CSL
- Spanish-first intake
- volunteers supporting people with limited connectivity
- a vetted set of partner organizations
- human responsibility for triage and sharing decisions

No field research or local service-provider integration has been performed for this
draft.

## End-to-end workflow

1. **Set up a response campaign.** Choose coverage, service types, intake questions, staff, working hours, escalation contacts, and available assistance. For Venezuela, support state → municipality → parish → community, with local aliases and landmarks rather than requiring a formal street address.
2. **Invite participation.** Volunteers share an official WhatsApp entry link through permitted outreach. Use an opaque campaign token, not names or phone numbers in the URL. A forwarded link identifies campaign origin, not a verified person or address. Opening the link alone does not submit a report; the person must send a message.
3. **Explain and ask.** Identify the NGO, explain what information is needed and who may see it, offer a human contact, and explain that submitting a report does not guarantee assistance. Record messaging permission separately from data-processing notice and any optional sharing consent.
4. **Collect a short assessment.** Ask whether the person is reporting for themselves, their household, or an area. Collect location, power and water status separately, when each was observed, outage onset if known, household size if relevant, remaining drinking water, and requested support. Allow unknown answers, correction, and pause/resume.
5. **Confirm the summary.** Show a short Spanish summary before submission. Free text and voice can supplement structured options; automated extraction is a draft until confirmed by the reporter or reviewed by staff.
6. **Create or update a case.** Link the assessment to a household and response case when assistance is requested. Accept area-only observations without forcing creation of a beneficiary profile. Repeat submissions update the timeline rather than silently replacing older observations.
7. **Triage and review.** Separate urgent needs, routine needs, missing information, potential duplicates, and comparable conflicting observations. High urgency and low evidence confidence may coexist.
8. **Share with partners.** Staff assign a case owner and mark triaged needs shareable.
   - Every partner sees aggregate demand on the map and dashboard.
   - Vetted partners also see and export a contactable list. The list contains only
     households that consented to sharing, in that partner's areas and categories.
   - Every view and export is logged.
   - The resident is told their request is now visible to organizations that may help.
9. **Follow up.** Ask the resident whether anyone helped, whether needs remain, and
   whether service was restored.
   - Partners may report outcomes too. These are kept separate from the resident's
     answer and never resolve a need on their own.
   - Reopen needs when needed.
   - A new outage is a new episode. Historical reports remain linked to their original
     observation times.

## Suggested first bot conversation

- “Hola, somos Metron Reporter. Recogemos información sobre cortes de luz y agua y la compartimos con organizaciones que pueden ayudar. No entregamos ayuda directamente y reportar no garantiza ayuda. Los datos los gestiona Ciudadanía Sin Límites. Puedes pedir hablar con una persona.”
- “¿Reportas por tu hogar, por otra persona o por tu comunidad?”
- “¿En qué comunidad estás? Puedes escribir una referencia; compartir ubicación es opcional.”
- “¿Cómo está la electricidad ahora? Disponible / Sin servicio / Intermitente / No sé.”
- “¿Cómo está el agua por tubería ahora? Disponible / Sin servicio / Intermitente / No sé.”
- For each affected service: “¿Desde cuándo? ¿Cuándo lo comprobaste por última vez?” Accept approximate times.
- “¿Tu hogar tiene agua para beber? Sí / Poca / No / No sé.” If useful, ask for approximate days remaining, explicitly permitting unknown.
- “¿Cuántas personas necesitan apoyo? ¿Qué apoyo necesitan?”
- “¿Hay una necesidad urgente que debamos revisar con una persona?”
  - A "yes" sends the agreed emergency and partner contacts immediately and queues
    staff review.
  - Keep detailed health information out of the default flow. Collect only
    operational accommodation needs, through an appropriate reviewed process.
- “¿Aceptas que compartamos tu contacto y tu necesidad con organizaciones que pueden ayudar en tu zona? Sí / No.”
  - This is asked separately from messaging permission.
  - A "no" still records the need. It just keeps the need off partner lists.
- Confirm the answers and provide a reference.
  - Explain that, with consent, the request may be shared with organizations, and that
    CSL does not control whether or when they respond.
  - Mention `ESTADO` for updates, and offer correction or human assistance.

Keep the initial path short with branching questions. Do not require photos, identity documents, GPS, a complete roster of household members, or a diagnosis to submit. The bot is not an emergency dispatch service; local escalation instructions must be agreed with the operating NGO before launch.

## Service-specific intake and fulfillment

In the pilot, only the **intake** parts of this section apply: the questions, and the
need details passed to partners. The **coordinator workflow**, stock, run, and
site-capacity paragraphs describe NGO-run fulfillment. That is deferred
(`DOM-090` in the requirements) because partners fulfill with their own tools.

### Water deliveries

Ask whether the water is needed for drinking or other household use, how many people need it, approximate remaining supply, desired quantity if known, delivery location/landmark, availability window, and whether containers or help receiving the water are needed. Do not require the household to estimate liters: a caseworker may propose a quantity under an NGO-approved allocation policy and record that basis. Keep requested, approved, allocated, and delivered quantities distinct.

Spanish branch: “¿Necesitas agua para beber, para otros usos o ambas?”; “¿Para cuántas personas?”; “¿Cuánta agua les queda aproximadamente?”; “¿Tienen recipientes para recibirla?”; “¿Dónde y cuándo podrían recibir la entrega?”

Coordinator workflow: review need → reserve suitable water supply → assign delivery run and time window → dispatch → record actual liters and unsuccessful delivery reasons → request recipient confirmation. Record supply suitability and the NGO's release/check reference; the application must not infer that water is safe to drink from appearance or a reporter's assertion. Do not substitute non-drinking supply for a drinking-water allocation.

A partial delivery leaves the remaining quantity open. Reconcile returned, lost, or undelivered quantities before making stock available again. Repeat requests in a new period are legitimate new demand, not automatically duplicates. Start with manually arranged delivery runs; route optimization can follow later.

### Charging access

Ask what devices need charging, device count, connector or charger availability, preferred time, whether the person can reach a site, and any assistance needed to access it. Assume phones and power banks for the first design; publish the NGO's actual supported device types before launch. Route unsupported equipment requests to staff rather than promising compatibility.

Spanish branch: “¿Qué necesitas cargar y cuántos equipos son?”; “¿Tienes cargador o cable?”; “¿Puedes llegar a un punto de carga?”; “¿En qué horario podrías ir?”

Coordinator workflow: select an operational compatible site → reserve device slots or offer a walk-in queue → provide confirmed location/hours → check in → record actual sessions and whether charging was successful. A proposed site or booking does not fulfill a need. If someone cannot travel, open a follow-up task; do not assume transport or mobile charging is available.

Site capacity is time-dependent. Operators declare safe simultaneous device capacity and slot duration based on their equipment. Track site status and when it was last checked; when a site loses power or closes, block new bookings and reassign affected reservations. Preserve the original reservation history. Missed appointments trigger contact or rescheduling, not a fraud flag.

### Operational priorities and dashboard

Pilot work queues: new, urgent, unassigned, human handoff, follow-up due, stale, and
not shareable (no consent). Each is filterable by need category and area.

The coordinator overview shows:

- open needs by category and parish
- needs triaged but not yet shared
- needs shared with no outcome after a set period
- follow-up replies
- partner export activity

The partner-facing demand map shows open needs per area and category, with small cells
suppressed. Never add liters, people, and devices into one quantity total.

Proposed urgency inputs are remaining drinking water, time waiting, stated urgency, and
access barriers, with a recorded human decision. Partners decide quantities; this draft
does not prescribe water consumption standards. An outage-duration estimate or
neighborhood consensus alone must not determine priority.

*Deferred fulfillment dashboard:* if CSL later runs fulfillment, add the following:

- Water: requested, reserved, and delivered liters; runs; partial deliveries.
- Charging: site status and capacity by slot, bookings, and sessions.

## Central platform

**Operations dashboard:** recent outage observations by area and service, freshness and coverage, urgent unassigned cases, open needs by category, assignments, and sharing backlog. An area with no reports is unknown, not unaffected. Maps show aggregate areas by default; precise household locations are restricted.

**Household/person CRM:** contact relationships, current location and location history, household membership if needed, assessments, open needs, contact permissions, assigned worker, assistance history, corrections, and complaints. A telephone is a contact endpoint, not a person identifier: phones may be shared or replaced.

**Review queue:** comparable conflicts, uncertain locations, stale observations, possible duplicates, extraction errors, and follow-up tasks. Reviewers see the evidence and reason for each flag.

**Partner sharing:** partner organizations, vetting, and scopes; the aggregate demand
map; the contactable list and watermarked exports for vetted partners; sharing history
per household; and optional partner-reported outcomes. Sharing is consent-bound and
fully logged. Partners are the largest planned outflow of personal data, so they
receive the minimum fields.

**Analytics:**

- invitation-to-intake completion, when attribution is available
- reporting coverage and age of observations
- median and 90th percentile time to first human action
- share of needs shared within 48 hours
- unresolved needs
- resident-reported and partner-reported outcome rates, kept separate

Always separate reports, deduplicated households, estimated people, and outcomes. These submissions are not a representative estimate of the population without a sampling design.

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

Roles initially: volunteer, caseworker, reviewer, coordinator, organization administrator. Volunteers see only assigned work and the minimum needed contact information. Invitations can be reusable campaign links or individually issued links; neither proves identity.

### Contacts, households, and permissions

```text
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

### Cases, needs, and partner sharing (pilot)

```text
case_record(id, organization_id, household_id, campaign_id?, status,
            assigned_membership_id?, opened_at, closed_at?, closure_reason?)
case_assessment(id, organization_id, case_id, assessment_id)
need(id, organization_id, case_id, assessment_id, category, requested_quantity?,
     unit?, period_start?, period_end?, urgency, urgency_reasons,
     status, shareable, shareable_reason?, last_confirmed_at,
     resolution_reason?, supersedes_need_id?)
partner_organization(id, organization_id, name, vetting_status,
                     responsible_contact_reference, statement_version,
                     may_disclose_name, vetted_by_membership_id?, vetted_at?)
partner_scope(id, organization_id, partner_organization_id, area_id, category)
share_event(id, organization_id, partner_organization_id, actor_membership_id,
            need_id, channel, fields_shared, export_record_id?, occurred_at)
export_record(id, organization_id, requested_by_membership_id,
              partner_organization_id?, scope_json, row_count, watermark_id,
              object_reference, expires_at, created_at)
need_outcome(id, organization_id, need_id, source, outcome, quantity?, unit?,
             reported_by_membership_id?, partner_organization_id?,
             conversation_id?, reported_at)
case_event(id, organization_id, case_id, event_type, actor_membership_id?,
           occurred_at, details_json)
```

`need.category` is `water_drinking`, `water_other`, or `charging`.

- A partner user is an ordinary membership in the operating organization with the
  `partner` role and a `partner_organization_id`. This is not a separate tenant.
- `need_outcome.source` is `partner` or `resident`. Outcomes are facts. A need is
  resolved only by a CSL disposition.
- The partner contactable list is derived, not stored. It contains needs whose
  households have active sharing consent and are safe to contact, that are triaged,
  open, and shareable, and that are within a vetted partner's scope.
- Every list view or export writes `share_event` rows in the same transaction.

Needs may remain after service restoration. A case can include multiple outage episodes
through its assessments.

### Deferred: NGO-run fulfillment

The records below apply only if CSL or a partner later manages fulfillment inside this
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
records. They hold the intake details passed to partners. The remaining extensions
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

- Prefer a relational database with spatial support, such as PostgreSQL with PostGIS, for household/case relationships and geographic queries. This is an architecture proposal, not a verified deployment stack or version selection.
- Use organization-scoped composite foreign keys or equivalent enforced constraints on operational relationships, plus row-level access controls and API authorization. A client-supplied organization ID is not authorization.
- Enforce unique inbound provider message IDs per channel account. Use separate deduplicated delivery-status events; delivery updates can arrive more than once or out of order.
- Retain assessment and observation revisions. Never overwrite the historical fact that an earlier report was made; controlled deletion/anonymization for retention still applies.
- Validate nonnegative quantities, matching units, valid time ranges, recognized statuses, and valid relationship scope. Prevent self-links and duplicate observation-pair relations.
- Read partner exports from a consistent snapshot, and record their share events in the
  same transaction.
- If fulfillment is reinstated, lock or transact resource reservations so simultaneous
  coordinators cannot allocate the same remaining stock.
- Index organization + case status + assignee, organization + observation time + service, household + open case, provider identifiers, and spatial fields. Derive dashboard views rather than storing a second untraceable set of facts.
- Store media separately with restricted access and expiry. Encrypt contact details and sensitive location data; manage keys separately. Restrict and audit exports as well as on-screen access.

## Technical shape

```text
Volunteer invitation → Resident sends WhatsApp message
    → authenticated webhook → durable inbox/queue
    → resumable intake workflow → normalized assessments and observations
    → case/need creation + comparison rules + human review
    → triage, consent-bound partner sharing, resident follow-up
    → aggregate operational dashboard and analytics
```

Use a modular application with two distinct worker components: a TypeScript operational worker for intake, messaging, and domain commands, and a Python data worker for external-source ingestion and geospatial evidence processing. The operational worker uses pg-boss; Python claims application-owned jobs through a versioned internal API with leases, retries, and idempotent completion. Python never consumes pg-boss tables or changes aid decisions directly. See [component boundaries](components/README.md) and the [data-job contract](components/contracts/data-jobs.md). Acknowledge webhooks after durable acceptance; retry processing safely, quarantine failures, and allow operators to replay failed jobs. Store outbound messages in a transactional outbox to avoid losing acknowledgements and follow-ups. Monitor failures, queue lag, message delivery, and stuck conversations.

A deterministic conversation flow is sufficient for the pilot. Optional AI can transcribe, translate, or propose structured fields; retain provenance and confirmation. AI should not invent locations, decide that an outage claim is false, or approve/deny aid.

Power and connectivity disruptions also affect reporting. Include telephone/volunteer-assisted entry and resumable conversations. Record when conditions were observed separately from when delayed messages arrived. Design a field-friendly low-bandwidth interface; full offline synchronization can follow after the pilot establishes the need.

## Messaging and data handling constraints

WhatsApp's current Business Messaging Policy requires permission for proactive contact, approved templates for initiating Platform conversations, and approved templates outside the 24-hour window following a user's last message. It also requires clear escalation options for automation. Build opt-out handling and human handoff into the first release. A volunteer sharing a link does not authorize unrestricted automated follow-ups. See [WhatsApp Business Messaging Policy](https://business.whatsapp.com/policy).

Adopt an NGO-approved data-sharing and retention policy before live collection. OCHA describes responsible humanitarian data management as safe, ethical, and effective handling of personal and non-personal data, and identifies information-sharing protocols as a key operational mechanism. See [OCHA Centre for Humanitarian Data](https://centre.humdata.org/data-responsibility/).

Proposed product safeguards: avoid collecting political affiliation or identity documents; restrict exact locations; share aggregate patterns by default; suppress or combine small groups in shared analytics; give people correction and complaint routes; and define deletion across records, media, exports, and backup expiry. Permission withdrawal should stop optional future outreach and trigger the applicable handling process, rather than promising instantaneous erasure of every lawful operational record. Local privacy, hosting, and cross-border requirements remain to be assessed with the NGO; this document makes no jurisdiction-specific legal conclusions.

## Delivery plan and pilot acceptance

**Stage 1 — operational design.** Interview NGO coordinators, volunteers, and participating households. Agree coverage, service definitions, available aid, response hours, escalation owners, required permissions, and success measures. Test Spanish wording and whether participants distinguish piped-water availability from drinking-water need.

**Stage 2 — intake and CRM.** Implement outreach attribution, WhatsApp ingestion, short structured intake, human handoff, household/case records, contact permissions, and assisted entry. Gate: complete an intake, resume after interruption, correct it, and retrieve it without duplicate creation after webhook replay.

**Stage 3 — triage and partner sharing.** Implement triage, shareable flags, partner
organizations with vetting and scopes, the contactable list and exports, share events,
share notices, resident follow-ups, and optional partner outcomes.

Gates:

- A simulated request can be tracked from intake through sharing to a resident-reported
  outcome.
- Partners never see non-consented, out-of-scope, or unvetted data.
- Consent withdrawal removes a household from later lists.
- Service restoration does not silently close unresolved needs.
- A household with two needs remains open after only one is resolved.
- A partner-reported "helped" does not resolve a need by itself.

**Stage 4 — evidence review and dashboard.** Add geographic comparison candidates, explicit review decisions, freshness indicators, aggregate maps, and coverage metrics. Gate: nearby disagreement never automatically rejects aid; different-time restoration is not flagged as a simultaneous conflict; missing reports are displayed as unknown.

**Stage 5 — bounded live pilot.** Launch in agreed communities with named staff and a manual fallback. Review completion, time to first action, unmet needs, correction volume, share rate,
outcome responses, and who is excluded by the channel.

Security gates:

- One organization cannot read another's records, including exports and background
  jobs.
- A partner cannot read beyond its vetted scope. Set quantitative targets with the NGO after measuring baseline workflow capacity.

**Stage 6 — multiple organizations.** Add scoped agreements, referrals, shared aggregate views, ownership handoffs, and revocation tests. Introduce sophisticated matching or infrastructure integrations only when data access and governance justify them.

Decisions made and still open are tracked in the
[requirements decisions table](components/REQUIREMENTS.md#decisions). Open launch
blockers:

- urgent referral content
- partner vetting criteria and data-handling statement
- contactable-list fields
- the WhatsApp integration agreement with the adapter contributor
