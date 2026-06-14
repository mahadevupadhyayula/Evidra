import pytest
from pydantic import ValidationError

from ai.schemas.company_context import CompanyContext


def valid_context():
    return {
        "source_type": "url",
        "source_url": "https://example.com",
        "company_description": "Example builds collaboration software.",
        "products_or_services": ["Collaboration software"],
        "target_users": ["Product teams"],
        "business_model_clues": [],
        "product_terminology": [],
        "strategic_themes": [],
        "source_references": [
            {
                "field": "company_description",
                "source_excerpt": "Example builds collaboration software",
            },
            {
                "field": "products_or_services",
                "source_excerpt": "collaboration software",
            },
            {
                "field": "target_users",
                "source_excerpt": "product teams",
            },
        ],
        "uncertain_fields": [],
    }


def test_company_context_accepts_valid_schema():
    context = CompanyContext.model_validate(valid_context())

    assert context.source_type == "url"
    assert context.products_or_services == ["Collaboration software"]


def test_company_context_rejects_extra_fields():
    data = valid_context()
    data["extra"] = "nope"

    with pytest.raises(ValidationError):
        CompanyContext.model_validate(data)


def test_company_context_requires_useful_content():
    data = valid_context()
    data.update(
        company_description=None,
        products_or_services=[],
        target_users=[],
        business_model_clues=[],
        product_terminology=[],
        strategic_themes=[],
    )

    with pytest.raises(ValidationError):
        CompanyContext.model_validate(data)
