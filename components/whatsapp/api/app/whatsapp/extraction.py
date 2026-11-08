"""Optional OpenAI extraction of typed answers into the report schema.

Amended OPW-023 (decided 2026-11-08): residents' free text is NOT sent to a
third-party AI service by default. When ``OPENAI_EXTRACTION=on``:

- only a typed answer that the deterministic parser could not read is sent,
  together with the question it answers;
- it is redacted first (phone numbers, e-mails, links, ID numbers) and capped
  at 280 characters; the sender's number, names, ids and address answers are
  never sent;
- the model must answer in a fixed JSON schema (Structured Outputs, strict);
- code validates every value (enums, ranges) and decides which database rows
  to write. The model never chooses ids and never writes SQL. Area names it
  returns are matched against the organization's own area list.

Any error (network, timeout, refusal, bad JSON) returns ``None`` and the bot
falls back to re-asking the question, so the conversation never depends on
OpenAI being up.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.models.report import DEVICE_TYPES, OBSERVATION_STATUSES, REMAINING_SUPPLY
from app.whatsapp.parsing import redact

log = logging.getLogger("whatsapp.extraction")


def _nullable(schema: dict) -> dict:
    t = schema.get("type")
    if "enum" in schema:
        return {"type": [t, "null"] if t else ["string", "null"],
                "enum": [*schema["enum"], None]}
    return {**schema, "type": [t, "null"]}


_FIELDS: dict[str, dict] = {
    "area_text": {"type": "string",
                  "description": "Parish, sector, neighborhood or landmark name as written."},
    "electricity_status": {"type": "string", "enum": list(OBSERVATION_STATUSES)},
    "electricity_since_days": {"type": "integer",
                               "description": "How many days ago the power outage began (0 = today)."},
    "water_status": {"type": "string", "enum": list(OBSERVATION_STATUSES),
                     "description": "Piped water (agua por tubería)."},
    "water_since_days": {"type": "integer",
                         "description": "How many days ago piped water stopped (0 = today)."},
    "needs_drinking_water": {"type": "boolean"},
    "drinking_people": {"type": "integer", "description": "People who need drinking water."},
    "drinking_liters": {"type": "number", "description": "Liters of drinking water needed."},
    "drinking_remaining_supply": {"type": "string", "enum": list(REMAINING_SUPPLY)},
    "needs_other_water": {"type": "boolean",
                          "description": "Water for cooking, washing or cleaning."},
    "other_water_people": {"type": "integer"},
    "needs_charging": {"type": "boolean",
                       "description": "Needs somewhere to charge phones or devices."},
    "charging_device_type": {"type": "string", "enum": list(DEVICE_TYPES)},
    "charging_device_count": {"type": "integer"},
    "urgent": {"type": "boolean",
               "description": "Someone is at risk today (no drinking water, medical device)."},
    "dont_know": {"type": "boolean",
                  "description": "The resident says they do not know the answer."},
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(_FIELDS),
    "properties": {k: _nullable(v) for k, v in _FIELDS.items()},
}

_SYSTEM = (
    "You extract facts from a short WhatsApp reply written by a resident of Caracas, "
    "Venezuela, in Spanish. The reply answers the question shown. Fill a field only "
    "when the resident states it explicitly; otherwise use null. Never guess. Never "
    "include names, phone numbers or addresses in any field. 'Luz' means electricity; "
    "'agua' without more context means piped water status. 'Se va y viene' means "
    "intermittent. Convert relative times to whole days ago (hoy=0, ayer=1, anteayer=2)."
)

_RANGES = {
    "electricity_since_days": (0, 60), "water_since_days": (0, 60),
    "drinking_people": (0, 500), "other_water_people": (0, 500),
    "drinking_liters": (0, 100_000), "charging_device_count": (1, 50),
}


def validate(raw: Any) -> dict | None:
    """Keep only well-typed, in-range, non-null values from a model answer."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for key, spec in _FIELDS.items():
        v = raw.get(key)
        if v is None:
            continue
        t = spec["type"]
        if t == "boolean" and not isinstance(v, bool):
            continue
        if t == "integer" and (not isinstance(v, int) or isinstance(v, bool)):
            continue
        if t == "number" and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            continue
        if t == "string" and not isinstance(v, str):
            continue
        if "enum" in spec and v not in spec["enum"]:
            continue
        if key in _RANGES:
            lo, hi = _RANGES[key]
            if not lo <= v <= hi:
                continue
        if key == "area_text":
            v = v.strip()[:120]
            if not v:
                continue
        out[key] = v
    return out


class Extractor(Protocol):
    def extract(self, *, question: str, answer: str) -> dict | None: ...


@dataclass
class OpenAIExtractor:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 15.0

    def extract(self, *, question: str, answer: str) -> dict | None:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",
                 "content": f"Pregunta: {question}\nRespuesta del residente: {redact(answer)}"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "report_fields", "strict": True, "schema": SCHEMA},
            },
        }
        try:
            resp = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            if msg.get("refusal") or not msg.get("content"):
                return None
            return validate(json.loads(msg["content"]))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            # Never log the answer itself.
            log.warning("openai extraction failed: %s", type(exc).__name__)
            return None


@dataclass
class FakeExtractor:
    """Test double: returns a canned result and records what it was sent."""

    result: dict | None = None
    calls: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.calls = []

    def extract(self, *, question: str, answer: str) -> dict | None:
        self.calls.append({"question": question, "answer": redact(answer)})
        return validate(self.result) if self.result is not None else None


_extractor: Extractor | None = None
_configured = False


def get_extractor() -> Extractor | None:
    """The configured extractor, or None when OPENAI_EXTRACTION is off."""
    global _extractor, _configured
    if not _configured:
        s = get_settings()
        if s.openai_extraction and s.openai_api_key:
            _extractor = OpenAIExtractor(s.openai_api_key, s.openai_model, s.openai_base_url,
                                         s.openai_timeout_seconds)
        _configured = True
    return _extractor


def set_extractor(extractor: Extractor | None) -> None:
    global _extractor, _configured
    _extractor, _configured = extractor, True
