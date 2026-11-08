"""Questionnaire definition and answers (CON-030, CON-031).

A questionnaire is data, never code. The conversation engine (OPW) walks its steps;
the web assisted-intake form renders the same definition. Each step maps its answer
to a stable ``ReportSubmission`` field path from ``MAPPABLE_FIELDS``, so a new
questionnaire version never changes the report schema.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, StringConstraints, model_validator

from .base import (
    AreaLevel,
    ContractModel,
    PrivacyProfileName,
    Slug,
    UtcInstant,
    Uuid,
    not_asked,
)

QUESTIONNAIRE_SCHEMA_VERSION = "1"

# Stable answer targets: ReportSubmission field paths. "needs[water_drinking]" selects
# the need of that category. Adding a path is backwards compatible; removing or
# re-purposing one needs a new questionnaire schema version.
MAPPABLE_FIELDS: frozenset[str] = frozenset(
    {
        "relationship",
        "area",
        "location.meeting_point_id",
        "location.address_text",
        "location.landmark",
        "observations[electricity].status",
        "observations[electricity].observed_at",
        "observations[electricity].outage_since",
        "observations[piped_water].status",
        "observations[piped_water].observed_at",
        "observations[piped_water].outage_since",
        "needs.categories",
        *(
            f"needs[{cat}].{field}"
            for cat in ("water_drinking", "water_other", "charging")
            for field in (
                "people_affected",
                "quantity",
                "remaining_supply",
                "stated_urgency",
                "access_notes",
                "preferred_times",
            )
        ),
        "permissions.refresh_prompts",
        "permissions.area_broadcasts",
        "permissions.contact_list",
        "permissions.notice_acknowledgement",
        "confirmation",
    }
)


class QuestionnaireRef(ContractModel):
    key: Slug
    version: Annotated[int, Field(ge=1)]


class LocalizedText(ContractModel):
    """Spanish (Venezuelan) is required; English is optional for staff UIs."""

    es: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    en: Annotated[str, StringConstraints(min_length=1, max_length=1024)] = not_asked()


class ChoiceOption(ContractModel):
    id: Slug
    label: LocalizedText
    value: Annotated[str, StringConstraints(pattern="^[a-z0-9_]{1,64}$")] = not_asked(
        description="The enum value written to the mapped field (defaults to the option id)."
    )


class ChoiceQuestion(ContractModel):
    type: Literal["choice"]
    options: Annotated[list[ChoiceOption], Field(min_length=1, max_length=10)]
    multiple: bool


class TextQuestion(ContractModel):
    type: Literal["text"]
    max_length: Annotated[int, Field(ge=1, le=2000)]


class NumberQuestion(ContractModel):
    type: Literal["number"]
    minimum: Annotated[int, Field(ge=0)]
    maximum: Annotated[int, Field(ge=1, le=1_000_000)]
    unit: Literal["liters", "people", "devices"] = not_asked()


class AreaQuestion(ContractModel):
    type: Literal["area"]
    levels: Annotated[list[AreaLevel], Field(min_length=1, max_length=4)]


class TimeAgoOption(ContractModel):
    id: Slug
    label: LocalizedText
    hours_ago_min: Annotated[int, Field(ge=0)]
    hours_ago_max: Annotated[int, Field(ge=0)] = not_asked(description="Omitted = open-ended.")


class TimeAgoQuestion(ContractModel):
    """'¿Desde hace cuánto?' — answers become approximate instants."""

    type: Literal["time_ago"]
    options: Annotated[list[TimeAgoOption], Field(min_length=1, max_length=10)]


Question = Annotated[
    Union[ChoiceQuestion, TextQuestion, NumberQuestion, AreaQuestion, TimeAgoQuestion],
    Field(discriminator="type"),
]


class Condition(ContractModel):
    """Branch condition on an earlier step's answer."""

    step_id: Slug
    op: Literal["equals", "in", "is_unknown", "answered"]
    values: Annotated[list[Slug], Field(max_length=10)] = not_asked()

    @model_validator(mode="after")
    def _values(self) -> "Condition":
        needs_values = self.op in ("equals", "in")
        if needs_values and not self.values:
            raise ValueError(f"op '{self.op}' requires values")
        if not needs_values and self.values is not None:
            raise ValueError(f"op '{self.op}' takes no values")
        if self.op == "equals" and self.values and len(self.values) != 1:
            raise ValueError("op 'equals' takes exactly one value")
        return self


class Branch(ContractModel):
    when: Annotated[list[Condition], Field(min_length=1, max_length=5)]
    goto: Slug


END = "end"


class Step(ContractModel):
    id: Slug
    prompt: LocalizedText
    question: Question
    maps_to: str
    allow_unknown: bool = Field(description="Offer 'No sé'; the answer maps to 'unknown'.")
    unknown_label: LocalizedText = not_asked()
    required: bool
    profiles: Annotated[list[PrivacyProfileName], Field(min_length=1, max_length=2)] = not_asked(
        description="Profiles that show this step; omitted = all. Address steps are standard-only."
    )
    branches: Annotated[list[Branch], Field(max_length=10)]
    next: Slug = Field(description="Default next step id, or 'end'.")

    @model_validator(mode="after")
    def _check(self) -> "Step":
        if self.maps_to not in MAPPABLE_FIELDS:
            raise ValueError(f"maps_to '{self.maps_to}' is not a stable report field")
        if self.unknown_label is not None and not self.allow_unknown:
            raise ValueError("unknown_label requires allow_unknown")
        return self


class QuestionnaireDefinition(ContractModel):
    """A versioned questionnaire. Validated against its schema; never executed."""

    schema_version: Literal["1"]
    key: Slug
    version: Annotated[int, Field(ge=1)]
    locale: Literal["es"]
    title: LocalizedText
    start: Slug
    steps: Annotated[list[Step], Field(min_length=1, max_length=60)]

    @model_validator(mode="after")
    def _graph(self) -> "QuestionnaireDefinition":
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("step ids must be unique")
        if END in ids:
            raise ValueError("'end' is reserved")
        known = set(ids)
        if self.start not in known:
            raise ValueError("start must name a step")
        for step in self.steps:
            targets = [step.next] + [b.goto for b in step.branches]
            for t in targets:
                if t != END and t not in known:
                    raise ValueError(f"step '{step.id}' points to unknown step '{t}'")
            for b in step.branches:
                for c in b.when:
                    if c.step_id not in known:
                        raise ValueError(f"step '{step.id}' branches on unknown step '{c.step_id}'")
        return self

    @property
    def ref(self) -> QuestionnaireRef:
        return QuestionnaireRef(key=self.key, version=self.version)


# ---- Answers (CON-031) ----------------------------------------------------


class ChoiceAnswer(ContractModel):
    kind: Literal["choice"]
    option_ids: Annotated[list[Slug], Field(min_length=1, max_length=10)]


class TextAnswer(ContractModel):
    kind: Literal["text"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class NumberAnswer(ContractModel):
    kind: Literal["number"]
    number: Annotated[int, Field(ge=0, le=1_000_000)]


class AreaAnswer(ContractModel):
    kind: Literal["area"]
    area_id: Uuid


class TimeAgoAnswer(ContractModel):
    kind: Literal["time_ago"]
    option_id: Slug


class UnknownAnswer(ContractModel):
    """The reporter chose 'No sé'."""

    kind: Literal["unknown"]


AnswerValue = Annotated[
    Union[ChoiceAnswer, TextAnswer, NumberAnswer, AreaAnswer, TimeAgoAnswer, UnknownAnswer],
    Field(discriminator="kind"),
]


class QuestionAnswer(ContractModel):
    """One original answer, kept verbatim alongside the mapped report (CON-031)."""

    step_id: Slug
    value: AnswerValue
    answered_at: UtcInstant
