from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_required_text(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("This field is required.")
    return text


def normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.replace("\n", ",").split(",")
    else:
        raw_values = value
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)
    return values


class ExtractedEvidenceCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    problem: str | None = None
    role: str | None = None
    action: str | None = None
    result: str | None = None
    metric: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=12)
    competencies: list[str] = Field(default_factory=list, max_length=8)
    ownership_signal: str | None = None
    constraints: str | None = None
    tradeoffs: str | None = None
    missing_details: list[str] = Field(default_factory=list, max_length=8)
    source_excerpt: str
    source_location: str | None = None
    source_type: Literal["resume", "highlight"]
    source_highlight_id: int | None = None
    confidentiality_suggested: bool = False
    duplicate_key: str | None = None
    duplicate_reason: str | None = None

    @field_validator("title", "source_excerpt", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator(
        "problem",
        "role",
        "action",
        "result",
        "metric",
        "ownership_signal",
        "constraints",
        "tradeoffs",
        "source_location",
        "duplicate_key",
        "duplicate_reason",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)

    @field_validator("skills", "competencies", "missing_details", mode="before")
    @classmethod
    def clean_lists(cls, value: Any) -> list[str]:
        return normalize_text_list(value)

    @model_validator(mode="after")
    def validate_source_highlight_id(self) -> ExtractedEvidenceCard:
        if self.source_type == "highlight" and self.source_highlight_id is None:
            raise ValueError("Highlight evidence must include source_highlight_id.")
        if self.source_type == "resume" and self.source_highlight_id is not None:
            raise ValueError("Resume evidence cannot include source_highlight_id.")
        return self


class ExtractedEvidenceSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cards: list[ExtractedEvidenceCard] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_cards(self) -> ExtractedEvidenceSet:
        if not self.cards:
            raise ValueError("Evidence extraction must include at least one card.")
        return self
