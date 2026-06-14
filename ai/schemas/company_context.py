from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw_values = [value] if isinstance(value, str) else value
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)
    return values


class CompanyContextReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "company_description",
        "products_or_services",
        "target_users",
        "business_model_clues",
        "product_terminology",
        "strategic_themes",
    ]
    source_excerpt: str

    @field_validator("source_excerpt", mode="before")
    @classmethod
    def clean_source_excerpt(cls, value: Any) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Source excerpt is required.")
        return text


class CompanyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["url", "paste"]
    source_url: str | None = None
    company_description: str | None = None
    products_or_services: list[str] = Field(default_factory=list, max_length=8)
    target_users: list[str] = Field(default_factory=list, max_length=8)
    business_model_clues: list[str] = Field(default_factory=list, max_length=8)
    product_terminology: list[str] = Field(default_factory=list, max_length=12)
    strategic_themes: list[str] = Field(default_factory=list, max_length=8)
    source_references: list[CompanyContextReference] = Field(default_factory=list, max_length=12)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("source_url", "company_description", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        return normalize_optional_text(value)

    @field_validator(
        "products_or_services",
        "target_users",
        "business_model_clues",
        "product_terminology",
        "strategic_themes",
        "uncertain_fields",
        mode="before",
    )
    @classmethod
    def clean_text_lists(cls, value: Any) -> list[str]:
        return normalize_text_list(value)

    @model_validator(mode="after")
    def require_useful_context(self) -> CompanyContext:
        if not any(
            [
                self.company_description,
                self.products_or_services,
                self.target_users,
                self.business_model_clues,
                self.product_terminology,
                self.strategic_themes,
            ]
        ):
            raise ValueError("Company context must include at least one useful field.")
        return self
