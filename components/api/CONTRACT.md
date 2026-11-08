# Dashboard API — Contract (v0.1)

FastAPI service that serves the web dashboard. It **reads** the shared database
written by `whatsapp/api` (reports, conversations, inbound events) and manages
org settings. This document is the **stable contract** the frontend builds
against. Shapes here will not change after Step 1 (only fake → real data swaps
underneath in Step 2).

- Base URL (local): `http://localhost:8001`
- Interactive docs: `GET /docs` · OpenAPI JSON: `GET /openapi.json`
- **Report-centric**: the dashboard works with **reports**, not cases (cases are
  deferred in the pilot per `components/api/README.md`).

## Conventions

- **Auth**: JWT bearer, `Authorization: Bearer <token>` (same scheme as
  `whatsapp/api`). Get a token from `/auth/login` or `/auth/signup`.
- **Org scoping**: the organization is **always** derived from the token's
  membership — never from a request body or query param.
- **Privacy enforced in the API**: every response that can carry personal fields
  (phone, name, precise location) is filtered by the org's data-protection
  **preset** *before* it leaves the API:
  - `standard` — full records: name and full phone visible, precise location.
  - `protected` — phone masked (`•••••42`), name omitted (`null`), area-level location.
  - `minimal` — aggregates only: `/contacts` returns `[]`, `GET /reports/{id}`
    returns 404, and report-list rows have PII stripped. Dashboard
    summary/areas still work.
  - `custom` — the explicit per-field flags are used as stored.
- **Errors**: `{"error": {"code": ..., "message": ..., "details": ...}}`.
  Codes: `validation_error` (422), `permission_denied` (403), `not_found` (404),
  `conflict` (409). Missing/invalid token → 403.
- **CORS**: credentialed CORS enabled for the configured frontend origins
  (default `http://localhost:5173`, `http://localhost:3000`).

Demo login: `demo@metron.org` / `demo-pass` (org "Miami Mutual Aid").

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/signup` | Create user + organization, return token |
| POST | `/auth/login` | Return JWT |
| GET | `/me` | Current user + memberships |
| GET/PUT | `/org/profile` | Org profile |
| GET | `/templates/collection` | Collection templates (6) |
| GET | `/templates/collection/recommended` | Recommended collection templates |
| GET | `/templates/dashboard` | Dashboard templates (one recommended) |
| PUT | `/org/bot-config` | Save bot config |
| PUT | `/org/dashboard-config` | Save dashboard config |
| GET/PUT | `/org/data-protection` | Data-protection settings |
| GET/PUT | `/org/channels` | Messaging channels |
| POST | `/contacts/import` | Import contacts CSV (multipart `file`) |
| GET | `/contacts` | Contacts with consent status |
| GET | `/dashboard/summary` | AI summary + metrics |
| GET | `/dashboard/areas` | Counts by neighborhood |
| GET | `/dashboard/feed?since=` | Recent messages w/ tags (polling) |
| GET | `/reports?status=` | Report list (filter by status) |
| GET | `/reports/{id}` | Report detail (transcript + extracted fields) |
| PATCH | `/reports/{id}` | Update status / notes / assignee |
| POST | `/campaigns` | Create campaign |
| GET | `/campaigns` | List campaigns |
| POST | `/ask` | Natural-language question → answer |
| GET | `/health` | Liveness |

---

## Auth

### POST `/auth/signup`
Request:
```json
{"email": "new@ngo.org", "password": "s3cret", "display_name": "Dir",
 "org_name": "Helping Hands", "org_type": "NGO"}
```
`org_type` ∈ `NGO | NPO | community | foundation | other`. Response: same as login.

### POST `/auth/login`
Request: `{"email": "demo@metron.org", "password": "demo-pass"}`
```json
{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer"}
```

### GET `/me`
```json
{
  "id": "user-demo",
  "email": "demo@metron.org",
  "display_name": "",
  "memberships": [
    {"organization_id": "org-demo", "organization_name": "Miami Mutual Aid", "role": "org_admin"}
  ]
}
```

---

## Org profile & onboarding

### GET/PUT `/org/profile`
```json
{
  "name": "Miami Mutual Aid",
  "type": "community",
  "mission": "Coordinate power and water relief across Miami-Dade neighborhoods.",
  "region": "Miami-Dade, FL",
  "languages": ["en", "es", "ht"],
  "population_served": "Low-income and elderly residents in flood-prone areas",
  "team_size": 12
}
```

### GET `/templates/collection`
Returns 6 templates: `power_water_outages`, `food_security`, `elderly_check_ins`,
`disaster_needs`, `beneficiary_feedback`, `aid_confirmation`. One element:
```json
{
  "id": "power_water_outages",
  "name": "Power & Water Outages",
  "description": "Track electricity and piped-water status and needs.",
  "questions": [
    {"key": "power_status", "label": "¿Cómo está la electricidad?", "field_type": "choice",
     "options": ["available", "unavailable", "intermittent", "unknown"]},
    {"key": "water_status", "label": "¿Cómo está el agua?", "field_type": "choice",
     "options": ["available", "unavailable", "intermittent", "unknown"]},
    {"key": "household_size", "label": "¿Cuántas personas hay en casa?", "field_type": "number", "options": null},
    {"key": "urgent_needs", "label": "¿Hay una necesidad urgente?", "field_type": "text", "options": null}
  ],
  "fields": ["power_status", "water_status", "household_size", "urgent_needs", "area"]
}
```
`field_type` ∈ `text | choice | number | boolean | location`.

### GET `/templates/collection/recommended`
```json
{
  "recommended_collection_ids": ["power_water_outages", "elderly_check_ins"],
  "reason": "Based on your region and population served (outage-prone, elderly residents)."
}
```

### GET `/templates/dashboard`
Three templates (`needs_overview` recommended, `map_first`, `case_management`):
```json
{
  "id": "needs_overview",
  "name": "Needs Overview",
  "description": "Summary metrics, area breakdown, and a live feed.",
  "widgets": [
    {"key": "summary", "label": "AI Summary", "type": "metric"},
    {"key": "metrics", "label": "Key Metrics", "type": "metric"},
    {"key": "areas", "label": "By Neighborhood", "type": "list"},
    {"key": "feed", "label": "Live Feed", "type": "feed"}
  ],
  "recommended": true
}
```
Widget `type` ∈ `metric | map | feed | list | chart`.

### PUT `/org/bot-config`
```json
{"greeting": "Somos Miami Mutual Aid...", "language_default": "es",
 "collection_template_id": "power_water_outages", "ask_consent": true,
 "human_handoff_enabled": true}
```

### PUT `/org/dashboard-config`
```json
{"template_id": "needs_overview", "widgets": ["summary", "metrics", "areas", "feed"]}
```

---

## Data protection

### GET/PUT `/org/data-protection`
```json
{
  "preset": "standard",
  "store_names": true,
  "location_precision": "precise",
  "raw_message_retention_days": 90,
  "mask_phone_numbers": false,
  "redact_exports": false,
  "individual_records_roles": ["org_admin", "coordinator"],
  "audit_log_enabled": true
}
```
`preset` ∈ `standard | protected | minimal | custom`;
`location_precision` ∈ `area | precise`. These settings are **enforced server-side**:
set `mask_phone_numbers=true` and `/reports` + `/contacts` return masked phones;
set `store_names=false` and names come back `null`.

---

## Channels

### GET/PUT `/org/channels`
```json
{
  "channels": [
    {"channel": "whatsapp", "status": "connected", "identifier": "+1 305 555 0142", "mode": "shared_bot"},
    {"channel": "sms", "status": "disconnected", "identifier": null, "mode": "own_number"},
    {"channel": "telegram", "status": "disconnected", "identifier": null, "mode": "own_number"},
    {"channel": "email", "status": "disconnected", "identifier": null, "mode": "own_number"}
  ]
}
```
`status` ∈ `connected | disconnected | pending`; `mode` ∈ `shared_bot | own_number`.

---

## Contacts

### POST `/contacts/import`
Multipart form upload, field name `file` (CSV). Response:
```json
{"imported": 42, "skipped": 0, "errors": []}
```

### GET `/contacts`
Privacy-filtered (`standard` shown):
```json
[
  {"id": "c1", "name": "Marie Pierre", "phone": "+13055550142", "area": "Little Haiti",
   "consent_status": "granted", "last_contact_at": null},
  {"id": "c2", "name": "José Díaz", "phone": "+13055550199", "area": "Hialeah",
   "consent_status": "pending", "last_contact_at": null}
]
```
`consent_status` ∈ `granted | pending | declined | unknown`.

---

## Dashboard

### GET `/dashboard/summary`
```json
{
  "summary": "5 reports today across Miami Mutual Aid: 3 without power, 1 without water, 3 urgent. Little Haiti and Allapattah are the hardest hit.",
  "metrics": {"reports_today": 5, "without_power": 3, "without_water": 1, "urgent": 3},
  "generated_at": "2026-11-08T14:00:00+00:00"
}
```

### GET `/dashboard/areas`
```json
[
  {"area": "Little Haiti", "reports": 18, "without_power": 12, "without_water": 4, "urgent": 5},
  {"area": "Liberty City", "reports": 14, "without_power": 6, "without_water": 9, "urgent": 3}
]
```

### GET `/dashboard/feed?since=<iso8601>`
Poll with the returned `cursor` as `?since=`. 
```json
{
  "items": [
    {"id": "msg-1", "received_at": "2026-11-08T13:53:00+00:00", "area": "Little Haiti",
     "channel": "whatsapp", "preview": "Sin luz desde anoche, 3 personas mayores en casa.",
     "tags": ["no_power", "elderly", "urgent"], "report_id": "report-1"}
  ],
  "cursor": "2026-11-08T13:53:00+00:00"
}
```

---

## Reports (report-centric; replaces cases)

### GET `/reports?status=<status>`
```json
[
  {
    "id": "report-1", "area": "Little Haiti", "status": "confirmed", "urgent": true,
    "submitted_at": "2026-11-08T13:00:00+00:00", "source_channel": "whatsapp",
    "service_type": "electricity", "service_status": "unavailable",
    "tags": ["no_power", "elderly"], "reporter_name": "Marie Pierre",
    "reporter_phone": "+13055551000", "assignee": null
  }
]
```
`status` ∈ `draft | confirmed | review | superseded | withdrawn`.
`reporter_name`/`reporter_phone` reflect the data-protection preset (shown here
under `standard` = full records; `protected` → `null` name and `•••••00` phone).

### GET `/reports/{id}`
```json
{
  "id": "report-1", "area": "Little Haiti", "status": "confirmed", "urgent": true,
  "submitted_at": "2026-11-08T13:00:00+00:00", "source_channel": "whatsapp",
  "service_type": "electricity", "service_status": "unavailable",
  "tags": ["no_power", "elderly"], "reporter_name": "Marie Pierre",
  "reporter_phone": "+13055551000", "assignee": null, "notes": "",
  "transcript": [
    {"from": "reporter", "at": "2026-11-08T13:00:00+00:00", "text": "Hola, no tengo luz desde anoche."},
    {"from": "bot", "at": "2026-11-08T13:00:00+00:00", "text": "Gracias. ¿Cuántas personas hay en casa?"},
    {"from": "reporter", "at": "2026-11-08T13:00:00+00:00", "text": "Somos 3."}
  ],
  "extracted_fields": {
    "power_status": "unavailable", "water_status": "unknown", "household_size": 3,
    "urgent_needs": ["no_power", "elderly"], "days_without_water": null
  }
}
```

### PATCH `/reports/{id}`
Request (all fields optional): `{"status": "review", "notes": "Called back", "assignee": "user-2"}`.
Returns the updated `ReportDetail`.

---

## Campaigns

### POST `/campaigns`
```json
{"name": "November Outage Watch", "collection_template_id": "power_water_outages",
 "areas": ["Little Haiti", "Liberty City"], "starts_at": "2026-11-01T00:00:00+00:00", "ends_at": null}
```
### GET `/campaigns`
```json
[
  {"id": "camp-1", "name": "November Outage Watch", "collection_template_id": "power_water_outages",
   "areas": ["Little Haiti", "Liberty City", "Overtown", "Allapattah"], "status": "active",
   "starts_at": "2026-11-01T00:00:00+00:00", "ends_at": null}
]
```

---

## Ask (natural language)

### POST `/ask`
Request: `{"question": "which neighborhood is worst?"}`
```json
{
  "answer": "In the last 24 hours, Little Haiti had the most urgent reports (5), mostly elderly residents without power. Allapattah follows with medical-device charging needs.",
  "data": {"top_area": "Little Haiti", "urgent_count": 5, "question": "which neighborhood is worst?"}
}
```

---

## Status: fake vs real

**Everything above returns realistic FAKE data (Step 1).** Step 2 swaps the data
source to real queries against the shared DB, in this order: auth → dashboard
(summary, feed, reports) → org/onboarding → data protection → the rest. The
**response shapes do not change** — only the values become live.
