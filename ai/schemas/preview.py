from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.schemas.stories import normalize_optional_text, normalize_required_text

PROHIBITED_OUTCOME_PATTERN = re.compile(
    r"\b(offer probability|chance of (?:an )?offer|likelihood of (?:getting )?(?:the )?offer|"
    r"probability of success|guarantee(?:d|s)?|\d+(?:[,.]\d+)?\s*%\s*(?:likely|chance))\b",
    re.IGNORECASE,
)


def _reject_prohibited_text(value: str | None) -> str | None:
    if value and PROHIBITED_OUTCOME_PATTERN.search(value):
        raise ValueError("Preview must not include offer-probability or guarantee claims.")
    return value


class PreviewCompetency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    readiness: Literal["strong", "covered", "partial", "gap"]
    source_match_id: int | None = None
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    story_ids: list[int] = Field(default_factory=list, max_length=3)

    @field_validator("key", "label", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("evidence_ids", "story_ids", mode="before")
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


class PreviewStrength(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    explanation: str
    source_match_id: int | None = None
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    story_ids: list[int] = Field(default_factory=list, max_length=3)

    @field_validator("title", "explanation", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @field_validator("evidence_ids", "story_ids", mode="before")
    @classmethod
    def clean_ids(cls, value: Any) -> list[int]:
        return PreviewCompetency.clean_ids(value)


class PreviewGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    explanation: str
    recommended_next_step: str | None = None
    source_match_id: int | None = None
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    story_ids: list[int] = Field(default_factory=list, max_length=3)

    @field_validator("title", "explanation", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @field_validator("recommended_next_step", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return _reject_prohibited_text(normalize_optional_text(value))

    @field_validator("evidence_ids", "story_ids", mode="before")
    @classmethod
    def clean_ids(cls, value: Any) -> list[int]:
        return PreviewCompetency.clean_ids(value)


class EvidenceCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_evidence_count: int = Field(ge=0)
    result_backed_evidence_count: int = Field(ge=0)
    competencies_with_evidence_count: int = Field(ge=0)
    summary: str

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class StoryCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready_story_count: int = Field(ge=0)
    matched_competency_count: int = Field(ge=0)
    gap_competency_count: int = Field(ge=0)
    summary: str

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""


class MatchedStoryExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: int
    match_id: int
    title: str
    excerpt: str
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)

    @field_validator("title", "excerpt", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def clean_ids(cls, value: Any) -> list[int]:
        return PreviewCompetency.clean_ids(value)


class ReadinessPreviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_summary: str
    competencies: list[PreviewCompetency] = Field(min_length=5, max_length=5)
    strengths: list[PreviewStrength] = Field(min_length=3, max_length=3)
    gaps: list[PreviewGap] = Field(min_length=3, max_length=3)
    evidence_completeness: EvidenceCompleteness
    story_coverage: StoryCoverage
    matched_story_excerpt: MatchedStoryExcerpt
    prepkit_explanation: str

    @field_validator("role_summary", "prepkit_explanation", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_prohibited_text(normalize_required_text(value)) or ""

    @model_validator(mode="after")
    def require_strength_or_gap(self) -> ReadinessPreviewOutput:
        if not self.strengths and not self.gaps:
            raise ValueError("Preview must include at least one strength or gap.")
        return self
