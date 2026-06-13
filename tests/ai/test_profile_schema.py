import pytest
from pydantic import ValidationError

from ai.schemas.profile import ExtractedProfile


def test_profile_schema_normalizes_unknowns_and_lists():
    profile = ExtractedProfile.model_validate(
        {
            "full_name": "  ",
            "current_role": "Product Manager",
            "current_company": None,
            "years_experience": 8,
            "industries": "SaaS\nSaaS, Fintech",
            "functional_areas": ["Product", " product "],
            "skills": ["Roadmapping", "Discovery"],
            "tools": None,
            "education_summary": " MBA ",
            "career_summary": " Builds products ",
            "positioning_summary": " Product leader ",
            "uncertain_fields": ["current_company"],
        }
    )

    assert profile.full_name is None
    assert profile.industries == ["SaaS", "Fintech"]
    assert profile.functional_areas == ["Product"]
    assert profile.tools == []
    assert profile.education_summary == "MBA"


def test_profile_schema_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"full_name": None, "unsupported": "value"})


def test_profile_schema_rejects_sensitive_inference():
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"career_summary": "Candidate age appears senior."})


def test_profile_schema_rejects_unrealistic_years():
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"years_experience": 100})


def test_profile_schema_rejects_direct_sensitive_values():
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"career_summary": "Candidate appears female."})
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"career_summary": "Candidate appears Muslim."})
    with pytest.raises(ValidationError):
        ExtractedProfile.model_validate({"career_summary": "Candidate appears disabled."})


def test_profile_schema_does_not_reject_experience_as_sensitive_term():
    profile = ExtractedProfile.model_validate({"career_summary": "Product experience."})

    assert profile.career_summary == "Product experience."
