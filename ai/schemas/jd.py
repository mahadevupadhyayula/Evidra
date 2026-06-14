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


class JDCompetency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    source_excerpt: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("description", "source_excerpt", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)


class JDSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: Literal["technical", "domain", "leadership", "communication", "other"] = "other"
    source_excerpt: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def clean_source_excerpt(cls, value: Any) -> str | None:
        return normalize_optional_text(value)


class SeniorityExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation: str
    source_excerpt: str | None = None

    @field_validator("expectation", mode="before")
    @classmethod
    def clean_expectation(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def clean_source_excerpt(cls, value: Any) -> str | None:
        return normalize_optional_text(value)


class JDTheme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    source_excerpt: str | None = None

    @field_validator("theme", mode="before")
    @classmethod
    def clean_theme(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def clean_source_excerpt(cls, value: Any) -> str | None:
        return normalize_optional_text(value)


class JDAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    competencies: list[JDCompetency] = Field(default_factory=list, max_length=8)
    skills: list[JDSkill] = Field(default_factory=list, max_length=15)
    seniority_expectations: list[SeniorityExpectation] = Field(default_factory=list, max_length=8)
    likely_themes: list[JDTheme] = Field(default_factory=list, max_length=8)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("summary", mode="before")
    @classmethod
    def clean_summary(cls, value: Any) -> str:
        return normalize_required_text(value)

    @field_validator("uncertain_fields", mode="before")
    @classmethod
    def clean_uncertain_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_values = [item.strip() for item in value.replace("\n", ",").split(",")]
        else:
            raw_values = [str(item).strip() for item in value]
        values: list[str] = []
        seen: set[str] = set()
        for item in raw_values:
            if item and item.casefold() not in seen:
                seen.add(item.casefold())
                values.append(item)
        return values

    @model_validator(mode="after")
    def require_useful_analysis(self) -> JDAnalysis:
        if not self.competencies and not self.skills and not self.seniority_expectations:
            raise ValueError("JD analysis must include competencies, skills, or expectations.")
        return self
