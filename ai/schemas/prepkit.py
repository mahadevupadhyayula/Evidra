from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.schemas.preview import PROHIBITED_OUTCOME_PATTERN
from ai.schemas.stories import normalize_optional_text, normalize_required_text

SOURCE_TYPES = Literal[
    "opportunity", "company_context", "role_pack", "match", "story", "evidence", "preview"
]


def _reject_prohibited_text(value: str | None) -> str | None:
    if value and PROHIBITED_OUTCOME_PATTERN.search(value):
        raise ValueError("Prep Kit must not include offer-probability or guarantee claims.")
    return value


class PrepKitSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SOURCE_TYPES
    source_id: int | str | None = None
    source_field: str | None = None
    excerpt: str | None = None

    @field_validator("source_field", "excerpt", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return _reject_prohibited_text(normalize_optional_text(value))


class GroundedTextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    detail: str
    source_refs: list[PrepKitSourceRef] = Field(default_factory=list, min_length=1, max_length=8)
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    story_ids: list[int] = Field(default_factory=list, max_length=7)
    match_ids: list[int] = Field(default_factory=list, max_length=7)

    @field_validator("title", "detail", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @field_validator("evidence_ids", "story_ids", "match_ids", mode="before")
    @classmethod
    def clean_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        ids: list[int] = []
        for item in raw_values:
            item_id = int(item)
            if item_id not in ids:
                ids.append(item_id)
        return ids


class PrepKitAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_briefing_points: list[GroundedTextItem] = Field(min_length=1, max_length=6)
    fit_findings: list[GroundedTextItem] = Field(min_length=1, max_length=6)
    competency_findings: list[GroundedTextItem] = Field(min_length=1, max_length=7)
    story_recommendations: list[GroundedTextItem] = Field(min_length=1, max_length=7)
    question_themes: list[GroundedTextItem] = Field(min_length=1, max_length=12)
    concern_findings: list[GroundedTextItem] = Field(default_factory=list, max_length=5)
    missing_evidence_findings: list[GroundedTextItem] = Field(default_factory=list, max_length=7)
    practice_priority_findings: list[GroundedTextItem] = Field(min_length=1, max_length=5)
    seven_day_focus_areas: list[GroundedTextItem] = Field(min_length=1, max_length=7)
    checklist_findings: list[GroundedTextItem] = Field(min_length=1, max_length=12)


class RoleBriefing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_title: str
    company_name: str | None = None
    briefing: str
    source_refs: list[PrepKitSourceRef] = Field(default_factory=list, min_length=1, max_length=8)

    @field_validator("role_title", "briefing", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @field_validator("company_name", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return _reject_prohibited_text(normalize_optional_text(value))


class FitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    strengths: list[GroundedTextItem] = Field(min_length=1, max_length=5)
    gaps: list[GroundedTextItem] = Field(default_factory=list, max_length=5)

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class CompetencyCoverageItem(GroundedTextItem):
    competency_key: str
    coverage_level: Literal["strong", "covered", "partial", "gap"]

    @field_validator("competency_key", mode="before")
    @classmethod
    def clean_key(cls, value: Any) -> str:
        key = normalize_required_text(value)
        return re.sub(r"[^a-z0-9_\-]+", "_", key.casefold()).strip("_") or "competency"


class StoryMapItem(GroundedTextItem):
    recommended_story_id: int | None = None
    question_types: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("question_types", mode="before")
    @classmethod
    def clean_question_types(cls, value: Any) -> list[str]:
        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        return [
            normalize_required_text(item) for item in raw_values if normalize_optional_text(item)
        ]


class QuestionBankItem(GroundedTextItem):
    question: str
    recommended_story_id: int | None = None
    priority: Literal["high", "medium", "low"] = "medium"

    @field_validator("question", mode="before")
    @classmethod
    def clean_question(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class ConcernMapItem(GroundedTextItem):
    concern: str

    @field_validator("concern", mode="before")
    @classmethod
    def clean_concern(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class MissingEvidenceItem(GroundedTextItem):
    suggested_detail: str

    @field_validator("suggested_detail", mode="before")
    @classmethod
    def clean_suggestion(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class PracticePriorityItem(GroundedTextItem):
    priority_order: int = Field(ge=1, le=5)


class SevenDayPlanDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_number: int = Field(ge=1, le=7)
    focus: str
    tasks: list[GroundedTextItem] = Field(min_length=1, max_length=2)

    @field_validator("focus", mode="before")
    @classmethod
    def clean_focus(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class ChecklistItem(GroundedTextItem):
    category: Literal["role", "stories", "evidence", "practice", "logistics", "closing"]


class PrepKitArtifactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_briefing: RoleBriefing
    fit_summary: FitSummary
    competency_coverage: list[CompetencyCoverageItem] = Field(min_length=1, max_length=7)
    story_map: list[StoryMapItem] = Field(min_length=1, max_length=7)
    question_bank: list[QuestionBankItem] = Field(min_length=1, max_length=12)
    concern_map: list[ConcernMapItem] = Field(default_factory=list, max_length=5)
    missing_evidence: list[MissingEvidenceItem] = Field(default_factory=list, max_length=7)
    practice_priorities: list[PracticePriorityItem] = Field(min_length=1, max_length=5)
    seven_day_plan: list[SevenDayPlanDay] = Field(min_length=7, max_length=7)
    interview_checklist: list[ChecklistItem] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def require_days_one_to_seven(self) -> PrepKitArtifactOutput:
        day_numbers = [day.day_number for day in self.seven_day_plan]
        if sorted(day_numbers) != list(range(1, 8)):
            raise ValueError("Prep Kit seven-day plan must contain days 1 through 7 exactly once.")
        return self
