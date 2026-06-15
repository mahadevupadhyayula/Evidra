from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.schemas.stories import normalize_optional_text, normalize_required_text


class StoryMatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_key: str
    primary_story_id: int | None = None
    alternative_story_id: int | None = None
    competency_score: int = Field(ge=0, le=100)
    role_relevance_score: int = Field(ge=0, le=100)
    seniority_score: int = Field(ge=0, le=100)
    evidence_strength_score: int = Field(ge=0, le=100)
    company_context_score: int = Field(ge=0, le=100)
    explanation: str = ""
    jd_excerpt: str | None = Field(default=None, max_length=1200)
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    missing_signal: str | None = Field(default=None, max_length=800)
    recommended_emphasis: str | None = Field(default=None, max_length=800)

    @field_validator("competency_key", mode="before")
    @classmethod
    def clean_competency_key(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("explanation", mode="before")
    @classmethod
    def clean_explanation(cls, value: Any) -> str:
        return normalize_optional_text(value) or ""

    @field_validator("jd_excerpt", "missing_signal", "recommended_emphasis", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def clean_evidence_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        ids: list[int] = []
        for item in raw_values:
            evidence_id = int(item)
            if evidence_id not in ids:
                ids.append(evidence_id)
        return ids

    @model_validator(mode="after")
    def validate_story_selection(self) -> StoryMatchCandidate:
        if self.primary_story_id is None and not self.missing_signal:
            raise ValueError("A missing signal is required when no primary story exists.")
        if (
            self.primary_story_id is not None
            and self.alternative_story_id is not None
            and self.primary_story_id == self.alternative_story_id
        ):
            raise ValueError("Primary and alternative stories must be different.")
        return self


class StoryMatchSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[StoryMatchCandidate] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def require_unique_competencies(self) -> StoryMatchSet:
        keys = [match.competency_key for match in self.matches]
        if len(keys) != len(set(keys)):
            raise ValueError("Story match competencies must be unique.")
        return self
