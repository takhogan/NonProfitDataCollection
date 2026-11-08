"""Versioned boundary contracts (Pydantic v2) — the source of truth (CON-001).

Modules:

* ``base`` — strict base model and common types (CON-002, CON-003, CON-005)
* ``reports`` — report submission, draft, needs, location detail (CON-010, CON-011)
* ``aggregation`` — indicator, area-of-need and coverage cells (CON-012, CON-013)
* ``providers`` — provider orgs, activities, alerts, API keys, contact list (CON-014, CON-015)
* ``public`` — public dashboard models, standalone by design (CON-016)
* ``admin`` — privacy profile, policies, memberships, campaigns, meeting points,
  broadcasts, review (CON-017)
* ``events`` — normalized messaging events (CON-020)
* ``jobs`` — internal job payloads (CON-021)
* ``data_jobs`` — data-worker protocol and mock Monitor Ciudad record (CON-022, CON-023)
* ``questionnaires`` — questionnaire definition and answers (CON-030, CON-031)
* ``errors`` — error envelope (CON-040)
* ``registry`` — which models are exported as JSON Schema, and where
* ``common``, ``household`` — legacy auth and (deprecated) household contracts
"""
