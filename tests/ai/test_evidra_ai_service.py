import pytest

from ai.client import MockAIClient
from ai.services import AIProfileExtractionError, EvidraAIService


def valid_response():
    return {
        "full_name": "Alex Candidate",
        "current_role": "Product Manager",
        "current_company": "ExampleCo",
        "years_experience": 7,
        "industries": ["SaaS"],
        "functional_areas": ["Product Management"],
        "skills": ["Discovery"],
        "tools": ["Jira"],
        "education_summary": None,
        "career_summary": "Product manager with B2B SaaS experience.",
        "positioning_summary": "Customer-focused product leader.",
        "uncertain_fields": [],
    }


def test_extract_profile_returns_validated_profile():
    client = MockAIClient(responses=[valid_response()])

    resume_text = (
        "Alex Candidate Product Manager ExampleCo 7 SaaS Discovery Jira "
        "Confirmed resume text"
    )

    profile = EvidraAIService(client=client).extract_profile(resume_text)

    assert profile.full_name == "Alex Candidate"
    assert client.calls == [{"resume_text": resume_text, "retry_context": None}]


def test_extract_profile_retries_once_for_structural_failure():
    client = MockAIClient(responses=[{"bad": "shape"}, valid_response()])

    resume_text = "Product Manager ExampleCo 7 SaaS Discovery Jira Confirmed resume text"

    profile = EvidraAIService(client=client).extract_profile(resume_text)

    assert profile.current_role == "Product Manager"
    assert len(client.calls) == 2
    assert client.calls[1]["retry_context"]


def test_extract_profile_fails_after_one_retry():
    client = MockAIClient(responses=[{"bad": "shape"}, {"also": "bad"}])

    with pytest.raises(AIProfileExtractionError):
        EvidraAIService(client=client).extract_profile("Confirmed resume text")

    assert len(client.calls) == 2


def test_extract_profile_requires_confirmed_resume_text():
    with pytest.raises(AIProfileExtractionError):
        EvidraAIService(client=MockAIClient()).extract_profile("   ")


def test_extract_profile_nulls_ungrounded_role_and_company():
    client = MockAIClient(responses=[valid_response()])

    profile = EvidraAIService(client=client).extract_profile("Confirmed resume text")

    assert profile.current_role is None
    assert profile.current_company is None
    assert "current_role" in profile.uncertain_fields
    assert "current_company" in profile.uncertain_fields


def test_extract_profile_removes_unsupported_numeric_summary_claim():
    response = valid_response()
    response["current_role"] = None
    response["current_company"] = None
    response["career_summary"] = "Improved conversion by 42%."
    client = MockAIClient(responses=[response])

    profile = EvidraAIService(client=client).extract_profile("Confirmed resume text")

    assert profile.career_summary is None
    assert "career_summary" in profile.uncertain_fields
