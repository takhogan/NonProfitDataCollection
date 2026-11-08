"""Exported JSON Schemas are current and portable (CON-001, CON-005)."""
from __future__ import annotations

import json
import re

import pytest
from jsonschema import Draft202012Validator

from app.contracts import registry
from scripts import export_contracts

from ._util import CONTRACTS_DIR

FILES = {name: CONTRACTS_DIR / registry.relative_path(g, name) for (g, name) in registry.EXPORTED}


def test_exported_schemas_are_not_stale():
    stale = export_contracts.stale_files()
    assert not stale, f"run `python -m scripts.export_contracts`; stale: {stale}"


def test_check_mode_exit_code():
    assert export_contracts.main(["--check"]) == 0


@pytest.mark.parametrize("name", sorted(FILES))
def test_schema_is_valid_draft_2020_12(name):
    schema = json.loads(FILES[name].read_text("utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == registry.JSON_SCHEMA_DIALECT
    assert schema["x-contract-version"] == "v1"


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


@pytest.mark.parametrize("name", sorted(FILES))
def test_schema_is_portable(name):
    schema = json.loads(FILES[name].read_text("utf-8"))
    for node in _walk(schema):
        ref = node.get("$ref")
        if isinstance(ref, str):
            assert ref.startswith("#/"), f"non-local $ref {ref}"
        pattern = node.get("pattern")
        if isinstance(pattern, str):
            re.compile(pattern)
            # No lookarounds, named groups, or Unicode-dependent classes.
            for banned in ("(?", "\\d", "\\w", "\\s", "\\b", "\\p"):
                assert banned not in pattern, f"non-portable regex {pattern!r}"
        for key in node.get("patternProperties", {}):
            assert "(?" not in key
        # Optional fields never advertise a null default (CON-003).
        assert not ("default" in node and node["default"] is None)


def test_objects_forbid_additional_properties():
    for name, path in FILES.items():
        for node in _walk(json.loads(path.read_text("utf-8"))):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, f"{name}: open object {node.get('title')}"


def test_monitor_ciudad_schema_marked_assumed():
    schema = json.loads(FILES["monitor_ciudad_report"].read_text("utf-8"))
    assert schema["x-assumed"] is True
