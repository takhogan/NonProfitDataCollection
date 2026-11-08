# Web requirements

The React/TypeScript application, with three surfaces:

- the **provider portal**, the primary product
- the **operating-NGO console** (intake, data quality, administration)
- the **public dashboard**, if enabled

Spanish-first and low-bandwidth. Types are generated from the backend's OpenAPI.
Shared context: [../REQUIREMENTS.md](../REQUIREMENTS.md).

## Shell

- **WEB-001 (P0) Sign-in and context.**
  - Google sign-in, or email + password + TOTP (with enrollment on first use).
  - The current organization, role, and provider organization are always visible.
  - Navigation shows only what the role allows.
- **WEB-002 (P0) Role home screens.** Each role lands on its main view:
  - provider → areas of need
  - coordinator → coverage and data health
  - reviewer → review queue
  - intake volunteer → new report
  - analyst → indicators
  - admin → users and providers
- **WEB-003 (P0) Language, time, and units.** Spanish by default, with English
  available. Caracas time with relative age. Units are always shown. "aprox." marks
  approximate times.
- **WEB-004 (P0) Honest numbers.** Every number states:
  - its unit: reporters, households, people (known plus "unknown for N"), or needs
  - its time bucket
  - its freshness
  - its coverage label
  - its confidence label, with the reasons on hover or tap

  Suppressed cells read "datos insuficientes". Unknown areas are never shown as zero.
- **WEB-005 (P0) Save feedback.** No optimistic success for submissions, exports, or
  profile changes. Failed saves keep the input in memory and retry with the same
  operation key.
- **WEB-006 (P0) Performance.** NFR-03. Map libraries and tiles load only when a map is
  opened. Every map view also has a table or list alternative.
- **WEB-007 (P0) Status banner.** Shows intake lag, stale indicators, or degraded
  services.

## Provider portal

- **WEB-010 (P0) Areas of need.** A ranked table of areas (`API-041`) with category
  filters. It shows the ranking criteria. Each row shows active needs, reporters,
  people affected, urgency mix, coverage, freshness, and confidence.
- **WEB-011 (P0) Need map.** A choropleth by sector or parish and category, showing need
  level, with hatching for unknown and a distinct style for suppressed areas. It can
  toggle between service status (`electricity`/`piped_water`) and needs. No points are
  drawn. The basemap depends on D11.
- **WEB-012 (P0) Coverage view.** A map and table of `covered`/`uncovered`/`unknown` per
  area × category, with the activities behind each covered cell. "Uncovered, high
  need" is highlighted as the primary call to action.
- **WEB-013 (P0) Area detail.** Indicators over time, service status, active
  activities, external context (Monitor Ciudad, night lights) as a labelled separate
  section, and data quality notes.
- **WEB-014 (P0) Log activity.** A quick form for type, category, areas (multi-select),
  schedule, optional capacity, optional public location (from meeting points or public
  sites), visibility (all providers / internal only / public), and status. Saved
  activities appear on the coverage view immediately.
- **WEB-015 (P0) My activities.** List, edit, pause, or end activities. A one-tap
  "still active" confirmation. Unconfirmed activities are highlighted after 7 days.
- **WEB-016 (P0) Alerts.** Create subscriptions (area set × category × trigger), view
  recent alerts, mute or unmute.
- **WEB-017 (P0) Exports.** Aggregate CSV/XLSX of the current view (indicators,
  coverage, activities), suppressed.
- **WEB-018 (P0) API keys.**
  - Create a key (shown once), name it, choose its scope (contact list only if vetted),
    set an expiry, and revoke it.
  - Shows last-used dates.
  - Links to the API documentation (`API-062`).
- **WEB-019 (P0) Contact list (vetted providers).**
  - Rows within scope, with fields per profile: protective shows alias, sector, meeting
    point, and phone; standard shows name, address, and phone.
  - The phone appears as a tap-to-call or WhatsApp action.
  - A data-handling reminder shows on every view, with acknowledgement on first use.
  - Export is watermarked and single-use.
  - An explanation says why the list contains only opted-in reporters.

## Operating-NGO console

- **WEB-030 (P0) Assisted intake.** Mirrors the bot questionnaire:
  1. Relationship.
  2. Area picker (parish → sector, with aliases).
  3. Location by profile: meeting point picker, or address and landmark.
  4. Electricity and water status with times.
  5. Needs: drinking water, other-use water, and/or charging, with details.
  6. Urgency.
  7. Separate permission questions: refresh, area info, contact list.
  8. Summary.

  "No sé" is allowed throughout. Protective mode never shows name, address, or GPS
  fields.
- **WEB-031 (P0) Area-only report.** A community report skips all personal steps.
- **WEB-032 (P0) Report browser.** Filter reports by area, category, review state, and
  time. Detail is masked, and revealing a field requires a reason. No editing beyond
  corrections that create a new version.
- **WEB-033 (P0) Coverage and data health.**
  - The coordinator home screen shows:
    - sectors with no recent reports
    - stale indicators
    - review backlog
    - uncovered high-need areas
    - activities unconfirmed for 7+ days
    - intake volume
  - It points to where to send outreach or volunteers.
- **WEB-034 (P0) Meeting points.** Manage meeting points per sector, with a picker
  preview showing what residents see in the bot.
- **WEB-035 (P0) Broadcasts.** Choose a provider activity and template, preview the
  recipient count (never the list), approve, and send. Shows a history of past
  broadcasts.
- **WEB-036 (P0) Review queue and workspace.**
  - Tasks by reason and age.
  - Linked reports side by side, with rule reasons, external context, and the effect on
    aggregates.
  - The disposition (`DOM-072`) requires a rationale.
- **WEB-037 (P0) Campaigns.** Areas, staffed hours, questionnaire, display identity,
  urgent referral content, and entry links with QR codes.

## Administration

- **WEB-040 (P0) Users.** Invite, assign roles, deactivate, view sessions, revoke, and
  reset TOTP.
- **WEB-041 (P0) Providers.** Create provider organizations, set scope, responsible
  contact, and statement version. Vet or suspend with a reason. Invite users. View
  sharing and export history and API key usage.
- **WEB-042 (P0) Privacy profile.**
  - Shows the active profile in plain language.
  - An edit flow shows the consequences before activation: purge counts on tightening;
    on loosening, a new notice version that applies only to new reports, plus a
    second admin's confirmation.
- **WEB-043 (P0) Policies.** Refresh and expiry periods, the ranking method version,
  suppression *k*, alert dedup windows, broadcast limits, and export limits.
- **WEB-044 (P0) Public dashboard settings.** Enable or disable it (an instant kill
  switch), and set level, *k*, and delay within profile limits, with a preview of
  exactly what the public will see.
- **WEB-045 (P0) Audit.** Search by user, provider, API key, and time range.

## Public dashboard

- **WEB-050 (P0) Public view.** No login. It shows:
  - a parish or sector status and need map (per profile), with banded counts,
    freshness, and coverage
  - public provider activities (water points and charging points, with schedule)
  - a text explanation of what the data is and isn't (self-reported, not a census, may
    be incomplete), with unknown areas clearly marked
- **WEB-051 (P0) Public safety.** Uses only `/public/v1`. No personal data, no free text,
  no cookies or trackers, and fully cacheable. A "how to report" panel links to the
  WhatsApp entry.
- **WEB-052 (P1) Embeddable widget.** An area status widget that partners can embed.

## Client security

- **WEB-060 (P0) No persistent sensitive storage.** No personal data in localStorage,
  IndexedDB, or service-worker caches. Caches clear on logout and timeout.
- **WEB-061 (P0) Masking.** Reveals are masked by default, require a reason, and re-mask
  after 5 minutes.
- **WEB-062 (P0) Quick exit.** A visible "Salir" button and "revoke all my sessions".
- **WEB-063 (P0) No third-party scripts.** No trackers, a strict Content Security Policy,
  and no external fonts on authenticated pages.

## Fallback

- **WEB-070 (P0) Paper fallback.** Printable report forms with no personal fields in
  protective mode. Back-entry records the true observation time and the source
  `paper`.

## Deferred

- **WEB-090 (P2) Case management screens.** Only with `DOM-090`.
