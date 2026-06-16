import pytest
from pydantic import ValidationError

from ai.schemas.practice import PracticeFeedbackOutput


def valid_payload():
    return {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded answer"],
        "improvements": ["Add a result"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "What result would you emphasize?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }


def test_practice_feedback_schema_accepts_valid_payload():
    output = PracticeFeedbackOutput.model_validate(valid_payload())

    assert output.relevance_score == 4


def test_practice_feedback_schema_rejects_extra_fields():
    payload = valid_payload()
    payload["extra"] = "nope"

    with pytest.raises(ValidationError):
        PracticeFeedbackOutput.model_validate(payload)


def test_practice_feedback_schema_rejects_protected_attribute_evaluation():
    payload = valid_payload()
    payload["improvements"] = ["Change your accent."]

    with pytest.raises(ValidationError):
        PracticeFeedbackOutput.model_validate(payload)


def test_practice_feedback_schema_rejects_out_of_range_score():
    payload = valid_payload()
    payload["clarity_score"] = 6

    with pytest.raises(ValidationError):
        PracticeFeedbackOutput.model_validate(payload)


def test_practice_feedback_schema_requires_source_refs():
    payload = valid_payload()
    payload.pop("source_refs")

    with pytest.raises(ValidationError):
        PracticeFeedbackOutput.model_validate(payload)
