# Backend endpoints the web app still needs

The Dashboard API contract (`components/api/CONTRACT.md` v0.1) covers the core flow.
The mock in `src/api/product/mock.ts` matches it exactly. The items below are
features in the product brief that the contract does **not** yet expose. Each is
either mocked client-side or stubbed in the UI until an endpoint exists.

Legend: **[mocked]** = the UI calls a mock behind the same client interface;
**[UI-only]** = form exists, no persistence yet.

## Gaps

1. **Report-status workflow metadata** — `PATCH /reports/{id}` accepts `status`,
   `notes`, `assignee`, but there is no endpoint listing assignable team members.
   *Needs:* `GET /org/members` (id + display_name + role) to populate the assignee
   picker. Currently the picker uses `GET /me` memberships only. **[mocked]**

2. **Channel connect / disconnect flow** — `PUT /org/channels` saves the channel
   list, but there is no OAuth/number-verification handshake to actually *connect*
   WhatsApp/SMS/Telegram. *Needs:* `POST /org/channels/{channel}/connect` →
   returns a verification URL or code; webhook/callback to flip `status` to
   `connected`. Today the UI toggles status locally and saves the list. **[UI-only]**

3. **Per-contact consent confirmation** — `GET /contacts` returns `consent_status`,
   and import accepts a CSV, but there is no way to *record* that an operator
   confirmed opt-in. *Needs:* `PATCH /contacts/{id}` (`consent_status`) or an
   import-time `consent_confirmed` flag. The import UI collects the confirmation
   checkbox but cannot persist per-contact. **[UI-only]**

4. **Column mapping on import** — `POST /contacts/import` takes a raw CSV. The brief
   wants a column-mapping preview. *Needs:* either a preview endpoint
   (`POST /contacts/import/preview` → detected columns + sample rows) or a
   `mapping` form field on import. The UI previews/maps client-side, then uploads
   the raw file. **[mocked]**

5. **Export (respecting data-protection)** — brief asks for export from Settings,
   redacted per `redact_exports`. *Needs:* `GET /reports/export?format=csv` (or
   `/contacts/export`) returning a privacy-filtered file. Today the UI can only
   build a CSV from already-fetched (already-filtered) rows. **[mocked]**

6. **Audit log of who viewed/exported** — `data-protection.audit_log_enabled` is a
   stored flag with no read endpoint. *Needs:* `GET /org/audit-log` (actor, action,
   subject, at). The Settings page shows the toggle but cannot display entries. **[UI-only]**

7. **Campaign sending / progress** — `POST /campaigns` creates a campaign and
   `GET /campaigns` lists them with a `status`, but there is no "proactive
   check-in" send trigger or per-campaign progress (sent / replied / completed).
   *Needs:* `POST /campaigns/{id}/launch` and progress fields (or
   `GET /campaigns/{id}/stats`). The UI shows campaigns and a mocked progress bar. **[mocked]**

8. **Bot preview round-trip** — the bot editor shows a WhatsApp-style preview
   rendered client-side from the saved questions. A live "test this bot" endpoint
   (`POST /org/bot-config/preview` → simulated exchange) would make it real. **[mocked]**

9. **Dashboard trend chart data** — `case_management` dashboard template includes a
   `trend` (chart) widget, but there is no time-series endpoint. *Needs:*
   `GET /dashboard/trend?metric=&bucket=` → points over time. The chart uses
   mocked series. **[mocked]**

10. **Need map data** — `map_first` dashboard template has a `map` widget; there is
    no geo endpoint and (per data-protection) precise points may be withheld.
    *Needs:* `GET /dashboard/map` returning area-level counts with coarse
    centroids. Map widget is deferred / shows the area list as a fallback. **[mocked]**

## Notes / contract questions

- **Auth scheme.** The contract uses `Authorization: Bearer <JWT>`. The
  provider-portal README (`components/whatsapp/api`) called browser-stored bearer
  tokens unacceptable for staff (SEC-07) and specified HttpOnly cookies. For the
  hackathon we follow the Dashboard API contract (bearer). Revisit before any real
  deployment with sensitive data.
- **`/me` has no org settings completeness flag.** We infer "needs onboarding"
  heuristically (empty org mission / no saved dashboard config). A
  `GET /me` field like `onboarding_complete` would be cleaner.
