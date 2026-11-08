"""CON-042: shared fixtures through Pydantic and jsonschema; both must agree."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import registry
from app.contracts.base import to_wire

from ._util import FIXTURES_DIR, adapter, fixture_files, fixture_id, load, schema_validator

VALID = fixture_files("valid")
INVALID = fixture_files("invalid")


def test_every_fixture_model_has_valid_and_invalid_fixtures():
    for kind in ("valid", "invalid"):
        names = {p.name for p in (FIXTURES_DIR / kind).iterdir() if p.is_dir()}
        unknown = names - set(registry.FIXTURE_MODELS)
        assert not unknown, f"fixture dirs with no model: {unknown}"
        missing = set(registry.FIXTURE_MODELS) - names
        # Per-job schemas are covered by internal_job invalid fixtures as well.
        if kind == "invalid":
            missing -= {n for n in missing if n.endswith("_job")}
        assert not missing, f"models with no {kind} fixtures: {missing}"


@pytest.mark.parametrize("path", VALID, ids=fixture_id)
def test_valid_fixture_passes_pydantic(path: Path):
    name = path.parent.name
    payload = load(path)
    ta = adapter(name)
    from_python = ta.validate_python(payload)  # what FastAPI does with a parsed body
    from_json = ta.validate_json(path.read_bytes())
    assert from_python == from_json
    # Round trip: the wire form re-validates to the same value.
    wire = _wire(ta, from_python)
    assert ta.validate_python(json.loads(json.dumps(wire))) == from_python


@pytest.mark.parametrize("path", VALID, ids=fixture_id)
def test_valid_fixture_passes_jsonschema(path: Path):
    errors = list(schema_validator(path.parent.name).iter_errors(load(path)))
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("path", INVALID, ids=fixture_id)
def test_invalid_fixture_fails_pydantic(path: Path):
    ta = adapter(path.parent.name)
    with pytest.raises(ValidationError):
        ta.validate_python(load(path))
    with pytest.raises(ValidationError):
        ta.validate_json(path.read_bytes())


EXPORTED_INVALID = [p for p in INVALID if p.parent.name in registry.EXPORTED_BY_NAME]


@pytest.mark.parametrize("path", EXPORTED_INVALID, ids=fixture_id)
def test_invalid_fixture_fails_exported_jsonschema(path: Path):
    """For exported schemas the data worker relies on, jsonschema must also reject."""
    assert not schema_validator(path.parent.name).is_valid(load(path))


def _wire(ta, value):
    if hasattr(value, "model_dump"):
        return to_wire(value)
    return ta.dump_python(value, mode="json", exclude_unset=True)
