# Web requirements

The web application for CSL staff and volunteers and for partner organizations.
Spanish-first, mobile-friendly, and low-bandwidth. Shared context, roles, and decisions:
[../REQUIREMENTS.md](../REQUIREMENTS.md).

## Shell and general behavior

- **WEB-001 (P0) Sign-in and context.**
  - Sign in with Google, or with email + password + TOTP (with TOTP enrollment on
    first use).
  - The current role, and the partner organization if any, are always visible.
  - Navigation shows only what the role allows.
- **WEB-002 (P0) Role home screens.** Each role lands on its main task:
  - caseworker → my cases
  - coordinator → operations overview
  - reviewer → review queue
  - intake volunteer → new intake
  - partner → demand map and list
  - analyst → area dashboard
  - admin → users and partners
- **WEB-003 (P0) Language and time.**
  - Spanish by default, with English available.
  - Times are shown in Caracas time with relative age.
  - Units are always shown.
  - Approximate times are marked "aprox.".
- **WEB-004 (P0) Save feedback.** No optimistic success for shares, exports, or
  dispositions. A failed save keeps the data in memory and retries with the same
  operation key. Stale-version errors explain what changed.
- **WEB-005 (P0) System status banner.** Shows API, worker, or message backlog
  problems (`API-065`).
- **WEB-006 (P0) Performance budget.** NFR-03. Intake and the partner list are
  code-split from map routes, and no map library loads until a map is opened.

## Assisted intake

- **WEB-010 (P0) Guided intake form.** Mirrors the bot questionnaire:
  1. Reporting relationship.
  2. Area picker (parish → sector, with aliases) and landmark.
  3. Electricity and water status, each with "when observed" and "since when".
  4. Drinking water left.
  5. Needs: drinking water, other-use water, and/or charging, with their detail
     branches.
  6. Urgency.
  7. Contact; the notice is read from a script.
  8. Messaging permission, then a **separate** sharing-consent question.
  9. Summary confirmation.

  Every question allows "No sé".
- **WEB-011 (P0) Area-only path.** "Reporting for the community" skips household,
  contact, and consent steps (SEC-02).
- **WEB-012 (P0) Possible-match prompt.**
  - A known phone shows "linked to N households" without details.
  - The volunteer creates a new household, or a caseworker opens the existing one.
  - Households are never auto-merged.
- **WEB-013 (P0) Draft resume.** Drafts are kept only in memory and in server-side
  drafts (SEC-07).
- **WEB-014 (P0) Confirmation screen.** Shows the reference code and a script
  explaining that CSL does not deliver aid itself. With consent, the information may be
  shared with organizations that can help, and a report does not guarantee help.

## Household CRM and case detail

- **WEB-020 (P0) Household search.** Search by reference, exact phone, area, or name.
  Results show no contact details.
- **WEB-021 (P0) Household profile.**
  - Shows reference, area, landmark (revealed on demand), estimated members, and masked
    contacts with reveal-with-reason.
  - Shows permissions, sharing consent, and opt-out state, plus safe-to-contact flags.
  - Lists cases, complaints, and corrections.
- **WEB-022 (P0) Case detail.**
  - A timeline of assessments, observations, messages (metadata), shares, outcome
    facts, follow-ups, and review events.
  - One card per need showing its category, details, urgency, status, shareable flag,
    which partners received it and when, partner-reported outcomes, and
    resident-reported outcomes. Partner and resident outcomes are visibly distinct.
- **WEB-023 (P0) Case actions.**
  - Assign, set urgency with reasons, and edit need details.
  - Mark a need shareable or not shareable, with a reason.
  - Message the household with a template or within the window.
  - Request a follow-up, resolve with a disposition reason, add notes.
  - Close only when every need has a disposition; the UI explains what blocks closure.
- **WEB-024 (P0) Evidence flags are information.** Review flags never appear as
  eligibility warnings.
- **WEB-025 (P0) No-consent handling.** For a need without sharing consent, the case
  shows an "ask for consent" action (a template message) and explains that the need
  will not appear on partner lists.

## Queues and operations overview

- **WEB-030 (P0) Queues.**
  - Queues: new, urgent, unassigned, human handoff, follow-up due, stale, and not
    shareable.
  - Filters: category, parish/sector, urgency, age, assignee.
  - Items past the escalation threshold are highlighted.
- **WEB-031 (P0) Operations overview (coordinator).**
  - Open needs by category and parish.
  - Needs triaged but not yet shared.
  - Needs shared with no partner outcome after N days.
  - Follow-up replies, the handoff backlog, and partner export activity.
  - Categories are never summed into one total.
- **WEB-032 (P0) Handoff inbox.** Shows the transcript (subject to retention) and the
  time left in the window. Staff can reply, use a template, return the conversation to
  the bot, or close it.

## Map and aggregate dashboard

These screens are shared by CSL staff, analysts, and partners.

- **WEB-050 (P0) Area condition map.**
  - A choropleth by parish or sector per service, showing status mix, freshness, and
    unknown share.
  - Areas with no reports are styled **unknown** (hatched), never "OK".
  - Suppressed cells read "datos insuficientes".
  - No points are drawn.
  - The basemap depends on D11.
- **WEB-051 (P0) Time controls.** Last 6 hours, 24 hours, or 7 days, with history
  stepping.
- **WEB-052 (P0) External context layer.** A toggle layer for Monitor Ciudad (mock, P0)
  and night lights (P1), labelled with source, time, and limits, and visually distinct
  from resident reports.
- **WEB-053 (P0) Need demand layer.** A choropleth of open needs per area and category
  (households, people when known, urgency mix), suppressed. This is partners' main
  planning view.
- **WEB-054 (P0) Metrics panel.** Coverage, freshness, and demand by category. CSL staff
  also see time to first action, share rate, and outcome counts. Reports, households,
  and estimated people are always separate.
- **WEB-055 (P0) Aggregate export.** CSV of the current view, with suppression.

## Review

- **WEB-056 (P0) Review queue and workspace.**
  - Tasks by reason and age.
  - Linked observations side by side, with rule reasons, external indicators, and
    history.
  - The disposition requires a rationale and evidence.
- **WEB-057 (P0) Duplicate and merge review.** Minimal-field comparison. A reviewer
  proposes, a coordinator approves, and a merge can be reversed.
- **WEB-058 (P1) Manual evidence.** Attach a utility notice, field check, or phone
  verification.

## Partner portal

Built for partner staff on phones or laptops. Unvetted partners see only the map and
dashboard (WEB-050–055).

- **WEB-060 (P0) Contactable list (vetted partners).**
  - A table, or cards on mobile, of `PartnerListRow`s in the partner's scope.
  - Filters: category, parish/sector, urgency, and "new since my last visit".
  - Shows the reference code, sector, landmark, need, quantity or people, urgency,
    window, and access notes.
  - The phone appears as a tap-to-call or open-WhatsApp action, not printed text.
- **WEB-061 (P0) Data-handling reminder.** On first use, the partner acknowledges the
  current data-handling statement. A short reminder is shown above every list and
  export.
- **WEB-062 (P0) Export.**
  - "Descargar lista" downloads CSV or XLSX of the current filter.
  - A confirmation shows the row count and the watermark notice.
  - The download is single-use and expires.
  - When the rate limit is reached, the screen says when export is available again.
- **WEB-063 (P1) Report outcome.** On a row, record contacted / helped (optional
  quantity) / could not reach / not able to help, with one tap plus confirm. Recording
  is idempotent.
- **WEB-064 (P0) Scope transparency.** Shows the partner's configured areas and
  categories, and explains why some needs are not listed: no consent, not yet triaged,
  or out of scope.
- **WEB-065 (P1) Simple mode.** Larger text, icon-first layout, and a Spanish first-run
  guide.

## Security and privacy in the client

- **WEB-080 (P0) No persistent sensitive storage.** No household data in localStorage,
  IndexedDB, or service-worker caches. Caches clear on logout, role switch, and timeout
  (SEC-07).
- **WEB-081 (P0) Masking by default.** Phones, landmarks, and names are masked until
  revealed with a reason. Revealed values re-mask after 5 minutes.
- **WEB-082 (P0) Quick exit.** A visible "Salir" button. "Revoke all my sessions" is in
  the account menu.
- **WEB-083 (P0) No third-party scripts.** No analytics or trackers, and no external
  fonts on authenticated pages. A strict Content Security Policy.

## Administration

- **WEB-085 (P0) Users.** Invite, assign roles, deactivate, view sessions, revoke, and
  reset TOTP.
- **WEB-086 (P0) Partners.**
  - Create partner organizations, set scope (areas × categories), the responsible
    contact, the statement version, and the name-disclosure flag.
  - Vet and suspend, each with a reason.
  - Invite partner users.
  - View the partner's share and export history.
- **WEB-087 (P0) Campaigns.**
  - Configure areas, staffed hours, questionnaire, display identity (default "Metron
    Reporter"), and urgent referral content (D15).
  - Generate, revoke, and get a QR code for WhatsApp entry links.
- **WEB-088 (P0) Policies.** Version and activate triage, escalation, follow-up, expiry,
  retention, suppression, and export limits.
- **WEB-089 (P0) Audit.** Search by user or partner and time range. A sharing history
  view answers "who received this household's data".

## Fallback

- **WEB-090 (P0) Paper/phone fallback.** Printable intake forms with minimal data.
  - Back-entry records the true observation time and the source `paper`.
  - Printed sheets carry a handling warning and destroy-after date.

## Deferred

- **WEB-095 (P2) Fulfillment screens.** Water supply, allocation, run planning, field
  delivery recording, and charging site/slot/check-in screens, only if `DOM-090` is
  reinstated.
