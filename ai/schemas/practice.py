from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.schemas.stories import normalize_optional_text, normalize_required_text

PROTECTED_EVALUATION_PATTERN = re.compile(
    r"\b(accent|voice|appearance|looks?|facial|face|gender|race|ethnicity|age|disability|religion|pregnan\w*)\b",
    re.IGNORECASE,
)
PracticeSourceType = Literal["question", "story", "evidence", "prepkit", "answer"]


def _reject_protected_text(value: str | None) -> str | None:
    if value and PROTECTED_EVALUATION_PATTERN.search(value):
        raise ValueError("Practice feedback must not evaluate protected attributes.")
    return value


class PracticeSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: PracticeSourceType
    source_id: int | str | None = None
    source_field: str | None = None
    excerpt: str | None = None

    @field_validator("source_field", "excerpt", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return _reject_protected_text(normalize_optional_text(value))


class UnsupportedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    reason: str
    suggested_fix: str | None = None
    source_refs: list[PracticeSourceRef] = Field(default_factory=list, max_length=8)

    @field_validator("claim", "reason", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_protected_text(normalize_required_text(value)) or ""

    @field_validator("suggested_fix", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return _reject_protected_text(normalize_optional_text(value))


class PracticeFeedbackOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance_score: int = Field(ge=1, le=5)
    structure_score: int = Field(ge=1, le=5)
    specificity_score: int = Field(ge=1, le=5)
    ownership_score: int = Field(ge=1, le=5)
    impact_score: int = Field(ge=1, le=5)
    clarity_score: int = Field(ge=1, le=5)
    strengths: list[str] = Field(min_length=1, max_length=5)
    improvements: list[str] = Field(min_length=1, max_length=5)
    improved_answer: str
    follow_up_question: str
    unsupported_claims: list[UnsupportedClaim] = Field(default_factory=list, max_length=8)
    source_refs: list[PracticeSourceRef] = Field(min_length=1, max_length=12)

    @field_validator("strengths", "improvements", mode="before")
    @classmethod
    def clean_text_list(cls, value: Any) -> list[str]:
        raw_values = value if isinstance(value, list) else [value]
        return [
            _reject_protected_text(normalize_required_text(item)) or ""
            for item in raw_values
            if normalize_optional_text(item)
        ]

    @field_validator("improved_answer", "follow_up_question", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return _reject_protected_text(normalize_required_text(value)) or ""

    @model_validator(mode="after")
    def require_follow_up_question_mark(self) -> PracticeFeedbackOutput:
        if not self.follow_up_question.endswith("?"):
            raise ValueError("Follow-up question must be phrased as a question.")
        return self
