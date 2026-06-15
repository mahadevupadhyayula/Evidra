from __future__ import annotations

from typing import Any

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
    raw_values = value.replace("\n", ",").split(",") if isinstance(value, str) else value
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)
    return values


class GeneratedStory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_story_id: str
    title: str
    story_type: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    learning: str | None = None
    short_answer: str
    ninety_second_answer: str
    detailed_answer: str
    competency_tags: list[str] = Field(default_factory=list, max_length=12)
    seniority_signals: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[int] = Field(min_length=1, max_length=5)
    missing_details: list[str] = Field(default_factory=list, max_length=10)

    @field_validator(
        "client_story_id",
        "title",
        "short_answer",
        "ninety_second_answer",
        "detailed_answer",
        mode="before",
    )
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator(
        "story_type",
        "situation",
        "task",
        "action",
        "result",
        "learning",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)

    @field_validator("competency_tags", "seniority_signals", "missing_details", mode="before")
    @classmethod
    def clean_lists(cls, value: Any) -> list[str]:
        return normalize_text_list(value)

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


class GeneratedStorySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stories: list[GeneratedStory] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def require_stories(self) -> GeneratedStorySet:
        if not self.stories:
            raise ValueError("Story generation must include at least one story.")
        ids = [story.client_story_id for story in self.stories]
        if len(ids) != len(set(ids)):
            raise ValueError("Story client IDs must be unique.")
        return self


class StoryScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_story_id: str
    specificity_score: int = Field(ge=0, le=100)
    impact_score: int = Field(ge=0, le=100)
    ownership_score: int = Field(ge=0, le=100)
    clarity_score: int = Field(ge=0, le=100)
    missing_details: list[str] = Field(default_factory=list, max_length=10)
    scoring_notes: str | None = None

    @field_validator("client_story_id", mode="before")
    @classmethod
    def clean_client_story_id(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("missing_details", mode="before")
    @classmethod
    def clean_missing_details(cls, value: Any) -> list[str]:
        return normalize_text_list(value)

    @field_validator("scoring_notes", mode="before")
    @classmethod
    def clean_scoring_notes(cls, value: Any) -> str | None:
        return normalize_optional_text(value)


class StoryScoreSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[StoryScore] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def require_scores(self) -> StoryScoreSet:
        if not self.scores:
            raise ValueError("Story scoring must include at least one score.")
        ids = [score.client_story_id for score in self.scores]
        if len(ids) != len(set(ids)):
            raise ValueError("Story score client IDs must be unique.")
        return self
