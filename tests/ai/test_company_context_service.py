import pytest

from ai.client import AIClientError, MockAIClient
from ai.services import AICompanyContextExtractionError, EvidraAIService
from tests.ai.test_company_context_schema import valid_context

SOURCE_TEXT = "Example builds collaboration software for product teams."


def test_extract_company_context_retries_once_for_structural_failure():
    valid = valid_context()
    client = MockAIClient(responses=[{"source_type": "url"}, valid])

    context = EvidraAIService(client=client).extract_company_context(
        source_text=SOURCE_TEXT,
        source_type="url",
        source_url="https://example.com",
    )

    assert context.company_description == valid["company_description"]
    assert len(client.calls) == 2
    assert client.calls[1]["retry_context"]


def test_extract_company_context_raises_after_two_failures():
    client = MockAIClient(responses=[AIClientError("down"), AIClientError("down")])

    with pytest.raises(AICompanyContextExtractionError):
        EvidraAIService(client=client).extract_company_context(
            source_text=SOURCE_TEXT,
            source_type="paste",
        )

    assert len(client.calls) == 2


def test_extract_company_context_rejects_unsupported_source_reference():
    data = valid_context()
    for reference in data["source_references"]:
        reference["source_excerpt"] = "not in source"
    client = MockAIClient(responses=[data, data])

    with pytest.raises(AICompanyContextExtractionError):
        EvidraAIService(client=client).extract_company_context(
            source_text=SOURCE_TEXT,
            source_type="url",
            source_url="https://example.com",
        )

    assert len(client.calls) == 2


def test_extract_company_context_rejects_unsupported_field_value_with_valid_reference():
    data = valid_context()
    data["products_or_services"] = ["Unmentioned analytics platform"]
    data["source_references"] = [
        reference
        for reference in data["source_references"]
        if reference["field"] != "products_or_services"
    ]
    data["source_references"].append(
        {"field": "products_or_services", "source_excerpt": "collaboration software"}
    )
    client = MockAIClient(responses=[data, data])

    with pytest.raises(AICompanyContextExtractionError):
        EvidraAIService(client=client).extract_company_context(
            source_text=SOURCE_TEXT,
            source_type="url",
            source_url="https://example.com",
        )

    assert len(client.calls) == 2


def test_extract_company_context_rejects_empty_normalized_source_excerpt():
    data = valid_context()
    data["source_references"][0]["source_excerpt"] = "!!!"
    client = MockAIClient(responses=[data, data])

    with pytest.raises(AICompanyContextExtractionError):
        EvidraAIService(client=client).extract_company_context(
            source_text=SOURCE_TEXT,
            source_type="url",
            source_url="https://example.com",
        )

    assert len(client.calls) == 2
