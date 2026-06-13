from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SENSITIVE_TERMS = {
    "age",
    "date of birth",
    "dob",
    "gender",
    "female",
    "male",
    "woman",
    "man",
    "sex",
    "race",
    "black",
    "asian",
    "latino",
    "latina",
    "hispanic",
    "ethnicity",
    "religion",
    "hindu",
    "muslim",
    "christian",
    "jewish",
    "sikh",
    "buddhist",
    "caste",
    "marital",
    "married",
    "single parent",
    "pregnant",
    "disability",
    "disabled",
    "health condition",
    "political",
    "sexual orientation",
    "gay",
    "lesbian",
    "bisexual",
    "transgender",
}


class SensitiveInferenceError(ValueError):
    """Raised when AI output contains sensitive or demographic inference."""


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.replace("\n", ",").split(",")]
    else:
        raw_items = [str(item).strip() for item in value]
    seen: set[str] = set()
    items: list[str] = []
    for item in raw_items:
        if not item:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items


def contains_sensitive_inference(value: str) -> bool:
    normalized = value.casefold()
    for term in SENSITIVE_TERMS:
        pattern = r"(?<![a-z])" + re.escape(term) + r"(?![a-z])"
        if re.search(pattern, normalized):
            return True
    return False


class ExtractedProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    current_role: str | None = None
    current_company: str | None = None
    years_experience: int | None = Field(default=None, ge=0, le=80)
    industries: list[str] = Field(default_factory=list, max_length=10)
    functional_areas: list[str] = Field(default_factory=list, max_length=10)
    skills: list[str] = Field(default_factory=list, max_length=30)
    tools: list[str] = Field(default_factory=list, max_length=30)
    education_summary: str | None = None
    career_summary: str | None = None
    positioning_summary: str | None = None
    uncertain_fields: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "full_name",
        "current_role",
        "current_company",
        "education_summary",
        "career_summary",
        "positioning_summary",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)

    @field_validator(
        "industries",
        "functional_areas",
        "skills",
        "tools",
        "uncertain_fields",
        mode="before",
    )
    @classmethod
    def clean_text_list(cls, value: Any) -> list[str]:
        return normalize_text_list(value)

    @model_validator(mode="after")
    def reject_sensitive_inference(self) -> ExtractedProfile:
        values: list[str] = []
        for value in [
            self.full_name,
            self.current_role,
            self.current_company,
            self.education_summary,
            self.career_summary,
            self.positioning_summary,
        ]:
            if value:
                values.append(value)
        values.extend(self.industries)
        values.extend(self.functional_areas)
        values.extend(self.skills)
        values.extend(self.tools)
        values.extend(self.uncertain_fields)
        if any(contains_sensitive_inference(value) for value in values):
            raise SensitiveInferenceError("Profile output contains sensitive inference.")
        return self
