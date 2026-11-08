"""Shared helpers for contract tests."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import TypeAdapter

from app.contracts import registry

API_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = API_ROOT.parents[1] / "contracts"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"


def fixture_files(kind: str) -> list[Path]:
    return sorted((FIXTURES_DIR / kind).glob("*/*.json"))


def fixture_id(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def adapter(name: str) -> TypeAdapter:
    return TypeAdapter(registry.FIXTURE_MODELS[name])


@lru_cache(maxsize=None)
def schema_validator(name: str) -> Draft202012Validator:
    """Checked-in schema for exported types; an on-the-fly schema for API models."""
    if name in registry.EXPORTED_BY_NAME:
        group, _ = registry.EXPORTED_BY_NAME[name]
        schema = json.loads((CONTRACTS_DIR / registry.relative_path(group, name)).read_text("utf-8"))
    else:
        schema = registry.build_schema(registry.FIXTURE_MODELS[name])
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())
