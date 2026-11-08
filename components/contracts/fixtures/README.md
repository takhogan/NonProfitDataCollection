# Shared contract fixtures (CON-042)

`valid/<name>/*.json` must pass and `invalid/<name>/*.json` must fail. Each file is the
bare payload. `<name>` matches a schema file name under `../schemas/<group>/v1/`, or an
API model listed in `API_FIXTURE_MODELS` in
`whatsapp/api/app/contracts/registry.py`. Those API models' schemas ship in `openapi.json`.

- **Backend:** `pytest tests/contracts` (from `components/whatsapp/api`) validates every
  fixture with Pydantic, in both Python and JSON mode. It also validates every fixture
  with `jsonschema` against the checked-in schema files.
- **Data worker:** validate the `events`, `data-jobs`, and `questionnaires` fixtures
  against `../schemas/` with `jsonschema` (Draft 2020-12). The results must match.

Invalid fixtures are named for the rule they break, for example
`report_submission/false_for_unknown_supply` or `data_job_result/unavailable_with_zero_value`.
Some rules can't be written in JSON Schema: observation-window ordering and length, and
questionnaire graph checks. Those rules are enforced by Pydantic only, and are tested in
`tests/contracts/test_models.py` instead of here.

Regenerate the schemas with `python -m scripts.export_contracts`. Check for drift with
`--check`.
