import pytest
from pydantic import ValidationError

from ai.schemas.evidence import ExtractedEvidenceSet


def valid_card(**overrides):
    data = {
        "title": "Delivered outcome",
        "problem": None,
        "role": None,
        "action": "Led product work",
        "result": "Improved outcomes",
        "metric": None,
        "skills": ["Product"],
        "competencies": ["Execution"],
        "ownership_signal": "Led",
        "constraints": None,
        "tradeoffs": None,
        "missing_details": [],
        "source_excerpt": "Led product work",
        "source_location": "resume",
        "source_type": "resume",
        "source_highlight_id": None,
        "confidentiality_suggested": False,
        "duplicate_key": None,
        "duplicate_reason": None,
    }
    data.update(overrides)
    return data


def test_evidence_schema_accepts_valid_card():
    evidence = ExtractedEvidenceSet.model_validate({"cards": [valid_card()]})

    assert evidence.cards[0].title == "Delivered outcome"


def test_evidence_schema_requires_source_excerpt():
    with pytest.raises(ValidationError):
        ExtractedEvidenceSet.model_validate({"cards": [valid_card(source_excerpt="")]})


def test_highlight_card_requires_highlight_id():
    with pytest.raises(ValidationError):
        ExtractedEvidenceSet.model_validate(
            {"cards": [valid_card(source_type="highlight", source_highlight_id=None)]}
        )
