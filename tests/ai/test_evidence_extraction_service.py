import pytest

from ai.client import AIClientError, MockAIClient
from ai.services import AIEvidenceExtractionError, EvidraAIService


def test_extract_evidence_retries_once_for_invalid_structure():
    client = MockAIClient(
        responses=[
            {"cards": [{"title": "Missing required fields"}]},
            {
                "cards": [
                    {
                        "title": "Grounded card",
                        "problem": None,
                        "role": None,
                        "action": "Led product teams",
                        "result": None,
                        "metric": None,
                        "skills": [],
                        "competencies": [],
                        "ownership_signal": None,
                        "constraints": None,
                        "tradeoffs": None,
                        "missing_details": [],
                        "source_excerpt": "Led product teams",
                        "source_location": "resume",
                        "source_type": "resume",
                        "source_highlight_id": None,
                        "confidentiality_suggested": False,
                        "duplicate_key": None,
                        "duplicate_reason": None,
                    }
                ]
            },
        ]
    )

    evidence = EvidraAIService(client=client).extract_evidence(
        resume_text="Led product teams and delivered outcomes.",
        highlights=[],
        profile_context={},
        opportunity_context={},
    )

    assert len(client.calls) == 2
    assert evidence.cards[0].title == "Grounded card"


def test_extract_evidence_rejects_missing_source_reference():
    client = MockAIClient(
        responses=[
            {
                "cards": [
                    {
                        "title": "Ungrounded card",
                        "problem": None,
                        "role": None,
                        "action": None,
                        "result": None,
                        "metric": None,
                        "skills": [],
                        "competencies": [],
                        "ownership_signal": None,
                        "constraints": None,
                        "tradeoffs": None,
                        "missing_details": [],
                        "source_excerpt": "Not in the source",
                        "source_location": "resume",
                        "source_type": "resume",
                        "source_highlight_id": None,
                        "confidentiality_suggested": False,
                        "duplicate_key": None,
                        "duplicate_reason": None,
                    }
                ]
            },
            AIClientError("still bad"),
        ]
    )

    with pytest.raises(AIEvidenceExtractionError):
        EvidraAIService(client=client).extract_evidence(
            resume_text="Led product teams and delivered outcomes.",
            highlights=[],
            profile_context={},
            opportunity_context={},
        )

    assert len(client.calls) == 2


def test_extract_evidence_removes_unsupported_metric_and_adds_prompt():
    client = MockAIClient(
        responses=[
            {
                "cards": [
                    {
                        "title": "Metric card",
                        "problem": None,
                        "role": None,
                        "action": "Led product teams",
                        "result": None,
                        "metric": "99%",
                        "skills": [],
                        "competencies": [],
                        "ownership_signal": None,
                        "constraints": None,
                        "tradeoffs": None,
                        "missing_details": [],
                        "source_excerpt": "Led product teams",
                        "source_location": "resume",
                        "source_type": "resume",
                        "source_highlight_id": None,
                        "confidentiality_suggested": False,
                        "duplicate_key": None,
                        "duplicate_reason": None,
                    }
                ]
            }
        ]
    )

    evidence = EvidraAIService(client=client).extract_evidence(
        resume_text="Led product teams and delivered outcomes.",
        highlights=[],
        profile_context={},
        opportunity_context={},
    )

    assert evidence.cards[0].metric is None
    assert "Confirm the metric for this evidence." in evidence.cards[0].missing_details
