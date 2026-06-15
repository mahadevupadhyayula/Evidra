import pytest
from pydantic import ValidationError

from ai.schemas.matching import StoryMatchSet


def valid_match(**overrides):
    data = {
        "competency_key": "product_strategy",
        "primary_story_id": 1,
        "alternative_story_id": 2,
        "competency_score": 80,
        "role_relevance_score": 75,
        "seniority_score": 70,
        "evidence_strength_score": 85,
        "company_context_score": 60,
        "explanation": "Grounded fit.",
        "jd_excerpt": "Lead product strategy",
        "evidence_ids": [1],
        "missing_signal": None,
        "recommended_emphasis": "Emphasize evidence.",
    }
    data.update(overrides)
    return data


def test_story_match_schema_accepts_valid_payload():
    matches = StoryMatchSet.model_validate({"matches": [valid_match()]})
    assert matches.matches[0].competency_key == "product_strategy"


def test_story_match_schema_rejects_extra_fields():
    with pytest.raises(ValidationError):
        StoryMatchSet.model_validate({"matches": [valid_match(total_score=99)]})


def test_story_match_schema_requires_missing_signal_for_gap():
    with pytest.raises(ValidationError):
        StoryMatchSet.model_validate(
            {"matches": [valid_match(primary_story_id=None, missing_signal=None)]}
        )


def test_story_match_schema_rejects_duplicate_competency_keys():
    with pytest.raises(ValidationError):
        StoryMatchSet.model_validate({"matches": [valid_match(), valid_match()]})
