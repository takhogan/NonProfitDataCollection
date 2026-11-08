"""AI-suggested campaign fields, with a deterministic template fallback.

`suggest_fields` asks OpenAI (Structured Outputs, a strict JSON schema matching
`CampaignField`) for 5–8 fields tailored to the campaign's name, purpose, chosen
template, and the org profile. The result is validated with Pydantic. If the LLM
call fails for ANY reason (no key, network, bad JSON, validation) we fall back to
the template's default fields so a live demo never breaks.

Design rules enforced here (belt-and-suspenders around the model):
- `area` is always present (the model is told to include it; we inject it if not).
- Core fields are preferred when they fit; `core_key` is only set for kind="core".
- Custom fields are limited to the allowed kinds.
- 3–5 fields are marked `recommended`, each with a short rationale.
- The list is clamped to 5–8 fields.
"""
from __future__ import annotations

import json
import logging
from statistics import median as _median

from pydantic import ValidationError

from dash import schemas as S

log = logging.getLogger("dash.campaign_fields")

MIN_FIELDS = 5
MAX_FIELDS = 8


# ---- Core field catalog ----------------------------------------------------
# The built-in intake concepts a campaign can reuse. `area` is always included.

def _area_field() -> S.CampaignField:
    return S.CampaignField(
        id="area", label_es="Zona / barrio", label_en="Area / neighborhood",
        question_es="¿En qué zona o barrio se encuentra?",
        question_en="Which area or neighborhood are you in?",
        kind="core", core_key="area", required=True,
        rationale="Every report is mapped by area; needed for the dashboard map and breakdowns.",
        recommended=True,
    )


_CORE_FIELDS: dict[str, S.CampaignField] = {
    "area": _area_field(),
    "has_power": S.CampaignField(
        id="has_power", label_es="Electricidad", label_en="Has power",
        question_es="¿Tiene electricidad en este momento?",
        question_en="Do you currently have electricity?",
        kind="core", core_key="has_power",
        rationale="Power status is a core outage metric tracked on the dashboard.",
        recommended=True,
    ),
    "has_water": S.CampaignField(
        id="has_water", label_es="Agua", label_en="Has water",
        question_es="¿Tiene agua corriente?",
        question_en="Do you have running water?",
        kind="core", core_key="has_water",
        rationale="Water status is a core outage metric tracked on the dashboard.",
        recommended=True,
    ),
    "household_size": S.CampaignField(
        id="household_size", label_es="Personas en el hogar", label_en="Household size",
        question_es="¿Cuántas personas hay en el hogar?",
        question_en="How many people are in the household?",
        kind="core", core_key="household_size", unit="people",
        rationale="Sizes relief and prioritizes larger affected households.",
    ),
    "urgent": S.CampaignField(
        id="urgent", label_es="Urgente", label_en="Urgent",
        question_es="¿Es una situación urgente que requiere atención inmediata?",
        question_en="Is this an urgent situation needing immediate attention?",
        kind="core", core_key="urgent",
        rationale="Flags reports for urgent review in the queue.",
        recommended=True,
    ),
}


# ---- Template default fields (fallback + LLM context) ----------------------
# Keyed by collection_template_id. Each is a complete, valid 5–8 field set the
# demo can show even with no LLM. Area is prepended automatically.

def _choice(value: str, es: str, en: str) -> S.CampaignFieldOption:
    return S.CampaignFieldOption(value=value, label_es=es, label_en=en)


_TEMPLATE_FIELDS: dict[str, list[S.CampaignField]] = {
    "power_water_outages": [
        _CORE_FIELDS["has_power"],
        _CORE_FIELDS["has_water"],
        _CORE_FIELDS["household_size"],
        S.CampaignField(
            id="hours_without_power", label_es="Horas sin electricidad",
            label_en="Hours without power",
            question_es="¿Cuántas horas lleva sin electricidad?",
            question_en="How many hours have you been without power?",
            kind="duration", unit="hours", recommended=True,
            rationale="Shows how long outages have persisted per area.",
        ),
        _CORE_FIELDS["urgent"],
    ],
    "food_security": [
        S.CampaignField(
            id="days_of_food", label_es="Días de comida", label_en="Days of food",
            question_es="¿Para cuántos días tiene comida?",
            question_en="How many days of food do you have?",
            kind="number", unit="days", recommended=True,
            rationale="Identifies households closest to running out of food.",
        ),
        S.CampaignField(
            id="children_in_home", label_es="Niños en el hogar",
            label_en="Children in home",
            question_es="¿Hay niños en el hogar?",
            question_en="Are there children in the home?",
            kind="boolean", recommended=True,
            rationale="Prioritizes families with children for food relief.",
        ),
        _CORE_FIELDS["household_size"],
        _CORE_FIELDS["urgent"],
    ],
    "elderly_check_ins": [
        S.CampaignField(
            id="is_safe", label_es="¿Está a salvo?", label_en="Is safe",
            question_es="¿Está bien y a salvo en este momento?",
            question_en="Are you okay and safe right now?",
            kind="boolean", recommended=True,
            rationale="Core wellness signal for elderly check-ins.",
        ),
        S.CampaignField(
            id="needs_medication", label_es="Necesita medicamentos",
            label_en="Needs medication",
            question_es="¿Necesita medicamentos pronto?",
            question_en="Do you need medication soon?",
            kind="boolean", recommended=True,
            rationale="Surfaces medication gaps that need urgent follow-up.",
        ),
        _CORE_FIELDS["has_power"],
        _CORE_FIELDS["urgent"],
    ],
    "disaster_needs": [
        S.CampaignField(
            id="shelter_status", label_es="Estado del refugio",
            label_en="Shelter status",
            question_es="¿Cómo está su vivienda o refugio?",
            question_en="What is your housing / shelter status?",
            kind="choice", recommended=True,
            options=[
                _choice("safe", "Seguro", "Safe"),
                _choice("damaged", "Dañado", "Damaged"),
                _choice("displaced", "Desplazado", "Displaced"),
                _choice("unknown", "No sé", "Unknown"),
            ],
            rationale="Splits displaced vs. sheltered populations for triage.",
        ),
        _CORE_FIELDS["has_power"],
        _CORE_FIELDS["has_water"],
        _CORE_FIELDS["household_size"],
        _CORE_FIELDS["urgent"],
    ],
}

# Generic fallback when the template id is unknown or missing.
_GENERIC_FIELDS: list[S.CampaignField] = [
    _CORE_FIELDS["has_power"],
    _CORE_FIELDS["has_water"],
    _CORE_FIELDS["household_size"],
    _CORE_FIELDS["urgent"],
]


def template_default_fields(template_id: str | None) -> list[S.CampaignField]:
    """The deterministic field set for a template (area is always prepended)."""
    base = _TEMPLATE_FIELDS.get(template_id or "", _GENERIC_FIELDS)
    return _finalize([_area_field(), *base])


# ---- Normalization ---------------------------------------------------------

def _finalize(fields: list[S.CampaignField]) -> list[S.CampaignField]:
    """Enforce the output invariants: area present & first, unique ids, allowed
    kinds coherent, 5–8 fields, 3–5 recommended."""
    seen: set[str] = set()
    out: list[S.CampaignField] = []
    for f in fields:
        if f.id in seen:
            continue
        seen.add(f.id)
        out.append(_coerce(f))

    # Always include area, first.
    if "area" not in seen:
        out.insert(0, _area_field())
    else:
        out.sort(key=lambda f: f.id != "area")  # area to the front, stable otherwise

    # Clamp to 5–8. If we have too few, pad from the generic core set.
    if len(out) < MIN_FIELDS:
        for pad in _GENERIC_FIELDS:
            if pad.id not in seen:
                out.append(_coerce(pad))
                seen.add(pad.id)
            if len(out) >= MIN_FIELDS:
                break
    out = out[:MAX_FIELDS]

    _ensure_recommended(out)
    return out


def _coerce(f: S.CampaignField) -> S.CampaignField:
    """Drop fields that don't belong on this kind (core_key only on core, options
    only on choice, unit only on number/duration)."""
    data = f.model_dump()
    if data["kind"] != "core":
        data["core_key"] = None
    if data["kind"] != "choice":
        data["options"] = None
    if data["kind"] not in ("number", "duration"):
        data["unit"] = None
    return S.CampaignField(**data)


def _ensure_recommended(fields: list[S.CampaignField]) -> None:
    """Guarantee 3–5 recommended fields (in place)."""
    lo, hi = 3, 5
    rec = [f for f in fields if f.recommended]
    if len(rec) < lo:
        for f in fields:
            if not f.recommended:
                f.recommended = True
                if not f.rationale:
                    f.rationale = "Suggested as a high-signal field for this campaign."
            if sum(1 for x in fields if x.recommended) >= lo:
                break
    elif len(rec) > hi:
        for f in rec[hi:]:
            f.recommended = False


# ---- OpenAI Structured Outputs ---------------------------------------------

def _json_schema() -> dict:
    """Strict JSON schema for the LLM, matching CampaignField. Structured Outputs
    requires every property listed in `required` and additionalProperties:false."""
    option = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "value": {"type": "string"},
            "label_es": {"type": "string"},
            "label_en": {"type": "string"},
        },
        "required": ["value", "label_es", "label_en"],
    }
    field = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "description": "snake_case, unique"},
            "label_es": {"type": "string"},
            "label_en": {"type": "string"},
            "question_es": {"type": "string"},
            "question_en": {"type": "string"},
            "kind": {"type": "string",
                     "enum": ["core", "boolean", "number", "choice", "duration", "text"]},
            "core_key": {"type": ["string", "null"],
                         "enum": ["area", "has_power", "has_water",
                                  "household_size", "urgent", None]},
            "options": {"type": ["array", "null"], "items": option},
            "unit": {"type": ["string", "null"]},
            "required": {"type": "boolean"},
            "rationale": {"type": "string"},
            "recommended": {"type": "boolean"},
        },
        "required": ["id", "label_es", "label_en", "question_es", "question_en",
                     "kind", "core_key", "options", "unit", "required",
                     "rationale", "recommended"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"fields": {"type": "array", "items": field}},
        "required": ["fields"],
    }


_SYSTEM = (
    "You design short WhatsApp intake questionnaires for a humanitarian NGO "
    "collecting field reports in Spanish-speaking communities (Miami). "
    "Given a campaign and the org profile, propose 5 to 8 campaign fields.\n"
    "Rules:\n"
    "- ALWAYS include a field with id \"area\" and kind \"core\", core_key \"area\".\n"
    "- Prefer core fields when they fit the goal: set kind \"core\" and core_key to "
    "one of area|has_power|has_water|household_size|urgent.\n"
    "- Custom fields must use one of these kinds only: boolean, number, choice, "
    "duration, text. Set core_key to null for them.\n"
    "- For kind \"choice\", provide 2–5 options (value + label_es + label_en); "
    "otherwise options is null.\n"
    "- For kind \"number\" or \"duration\", set a short unit (e.g. days, hours, "
    "people); otherwise unit is null.\n"
    "- Provide both Spanish (es) and English (en) labels and questions. Questions "
    "should be short and natural for a chat.\n"
    "- Mark 3 to 5 fields as recommended:true, each with a one-sentence rationale.\n"
    "- Keep every field relevant to the campaign purpose."
)


def _build_prompt(req: S.SuggestFieldsRequest, org_profile: dict | None) -> str:
    profile = org_profile or {}
    lines = [
        f"Campaign name: {req.name}",
        f"Purpose: {req.purpose or '(not provided)'}",
        f"Template: {req.collection_template_id or '(none)'}",
        "Organization profile:",
        f"  mission: {profile.get('mission', '')}",
        f"  region: {profile.get('region', '')}",
        f"  population served: {profile.get('population_served', '')}",
        f"  languages: {', '.join(profile.get('languages', []) or [])}",
    ]
    return "\n".join(lines)


def _call_openai(req: S.SuggestFieldsRequest, org_profile: dict | None,
                 api_key: str, model: str) -> list[S.CampaignField]:
    """Raises on any failure; caller falls back to template defaults."""
    from openai import OpenAI  # imported lazily so the dep is optional locally

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_prompt(req, org_profile)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "campaign_fields",
                "strict": True,
                "schema": _json_schema(),
            },
        },
        temperature=0.4,
    )
    content = resp.choices[0].message.content or "{}"
    payload = json.loads(content)
    raw = payload.get("fields", [])
    fields = [S.CampaignField(**f) for f in raw]  # Pydantic validation
    if not fields:
        raise ValueError("LLM returned no fields")
    return fields


def suggest_fields(
    req: S.SuggestFieldsRequest,
    org_profile: dict | None,
    *,
    api_key: str,
    model: str,
) -> S.SuggestFieldsResponse:
    """Return 5–8 validated campaign fields. Falls back to template defaults on
    any LLM failure so the demo never breaks."""
    if api_key:
        try:
            fields = _call_openai(req, org_profile, api_key, model)
            return S.SuggestFieldsResponse(
                fields=_finalize(fields), source="llm", model=model,
            )
        except (ImportError, ValidationError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.warning("campaign field LLM call failed (%s); using template fallback", e)
        except Exception as e:  # network/auth/etc. — never break the demo
            log.warning("campaign field LLM call errored (%s); using template fallback", e)
    return S.SuggestFieldsResponse(
        fields=template_default_fields(req.collection_template_id),
        source="fallback", model=None,
    )


# ---- Typed aggregates over custom fields -----------------------------------

def _as_bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "si", "sí", "1", "y"):
            return True
        if s in ("false", "no", "0", "n"):
            return False
    return None


def _as_number(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _aggregate_one(field: S.CampaignField, values: list) -> S.FieldAggregate:
    """Compute the typed aggregate for one custom field from the raw answer values
    (already filtered to reports that answered it)."""
    agg = S.FieldAggregate(
        field_id=field.id, kind=field.kind,
        label_en=field.label_en, label_es=field.label_es,
        responses=0,
    )
    if field.kind == "boolean":
        bools = [b for b in (_as_bool(v) for v in values) if b is not None]
        agg.responses = len(bools)
        if bools:
            agg.yes_pct = round(100.0 * sum(1 for b in bools if b) / len(bools), 1)
    elif field.kind == "number":
        nums = [n for n in (_as_number(v) for v in values) if n is not None]
        agg.responses = len(nums)
        if nums:
            agg.avg = round(sum(nums) / len(nums), 2)
            agg.min = min(nums)
            agg.max = max(nums)
    elif field.kind == "duration":
        nums = [n for n in (_as_number(v) for v in values) if n is not None]
        agg.responses = len(nums)
        if nums:
            agg.median = round(float(_median(nums)), 2)
    elif field.kind == "choice":
        counts: dict[str, int] = {}
        allowed = {o.value for o in (field.options or [])}
        answered = 0
        for v in values:
            if v is None:
                continue
            key = str(v)
            if allowed and key not in allowed:
                continue
            counts[key] = counts.get(key, 0) + 1
            answered += 1
        # Seed every option at 0 so the shape is stable with no data.
        for o in (field.options or []):
            counts.setdefault(o.value, 0)
        agg.responses = answered
        agg.counts = counts
    else:  # text — no typed aggregate, just a response count
        answered = [v for v in values if v not in (None, "")]
        agg.responses = len(answered)
    return agg


def aggregate_results(campaign_id: str, fields: list[S.CampaignField],
                      answers: list[dict]) -> S.CampaignResults:
    """Build a CampaignResults from a campaign's custom fields and the answer rows.

    Core fields are skipped (their metrics live on the dashboard). Returns empty
    aggregates (responses=0) when there is no data yet."""
    aggregates: list[S.FieldAggregate] = []
    for f in fields:
        if f.kind == "core":
            continue
        values = [a[f.id] for a in answers if f.id in a and a[f.id] is not None]
        aggregates.append(_aggregate_one(f, values))
    return S.CampaignResults(
        campaign_id=campaign_id,
        total_reports=len(answers),
        aggregates=aggregates,
    )
