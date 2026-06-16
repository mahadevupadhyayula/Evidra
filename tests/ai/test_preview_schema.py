import pytest
from pydantic import ValidationError

from ai.schemas.preview import ReadinessPreviewOutput
from tests.previews.helpers import preview_response


def test_preview_schema_accepts_valid_output():
    match = type("M", (), {"id": 1})()
    story = type("S", (), {"id": 2, "title": "Story", "short_answer": "Excerpt"})()
    evidence = type("E", (), {"id": 3})()
    preview = ReadinessPreviewOutput.model_validate(preview_response(match, story, evidence))
    assert preview.competencies[0].readiness == "covered"


def test_preview_schema_rejects_offer_probability_claim():
    match = type("M", (), {"id": 1})()
    story = type("S", (), {"id": 2, "title": "Story", "short_answer": "Excerpt"})()
    evidence = type("E", (), {"id": 3})()
    data = preview_response(match, story, evidence)
    data["role_summary"] = "You have a 75% chance of offer."
    with pytest.raises(ValidationError):
        ReadinessPreviewOutput.model_validate(data)


def test_preview_schema_limits_free_preview_sections():
    match = type("M", (), {"id": 1})()
    story = type("S", (), {"id": 2, "title": "Story", "short_answer": "Excerpt"})()
    evidence = type("E", (), {"id": 3})()
    data = preview_response(match, story, evidence)
    data["strengths"] = data["strengths"] * 4
    with pytest.raises(ValidationError):
        ReadinessPreviewOutput.model_validate(data)


def test_preview_schema_requires_full_free_preview_counts():
    match = type("M", (), {"id": 1})()
    story = type("S", (), {"id": 2, "title": "Story", "short_answer": "Excerpt"})()
    evidence = type("E", (), {"id": 3})()
    data = preview_response(match, story, evidence)
    data["competencies"] = data["competencies"][:4]
    with pytest.raises(ValidationError):
        ReadinessPreviewOutput.model_validate(data)

    data = preview_response(match, story, evidence)
    data["gaps"] = data["gaps"][:2]
    with pytest.raises(ValidationError):
        ReadinessPreviewOutput.model_validate(data)
