import pytest

from ai.client import MockAIClient
from ai.services import AIAnswerEvaluationError, EvidraAIService

VALID_CONTEXT = {
    "question": {"question_id": "q1", "question": "Tell me about the approved story."},
    "answer_text": "I led the approved work and explained the result clearly.",
    "linked_story": {"id": 1, "short_answer": "I led the approved work."},
    "approved_evidence": [{"id": 1, "source_excerpt": "I led the approved work."}],
    "prepkit_context": {"id": 1, "practice_priorities": []},
}


def valid_response():
    return {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add detail"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "evidence", "source_id": 1}],
    }


def test_evaluate_answer_accepts_valid_feedback():
    service = EvidraAIService(client=MockAIClient(responses=[valid_response()]))

    output = service.evaluate_answer(**VALID_CONTEXT)

    assert output.clarity_score == 4


def test_evaluate_answer_retries_once_for_invalid_feedback():
    service = EvidraAIService(
        client=MockAIClient(responses=[{"clarity_score": 6}, valid_response()])
    )

    output = service.evaluate_answer(**VALID_CONTEXT)

    assert output.relevance_score == 4


def test_evaluate_answer_rejects_unknown_evidence_reference():
    bad = valid_response()
    bad["source_refs"] = [{"source_type": "evidence", "source_id": 999}]
    service = EvidraAIService(client=MockAIClient(responses=[bad, bad]))

    with pytest.raises(AIAnswerEvaluationError):
        service.evaluate_answer(**VALID_CONTEXT)


def test_evaluate_answer_rejects_unsupported_numeric_claim():
    bad = valid_response()
    bad["improved_answer"] = "I improved revenue by 999%."
    service = EvidraAIService(client=MockAIClient(responses=[bad, bad]))

    with pytest.raises(AIAnswerEvaluationError):
        service.evaluate_answer(**VALID_CONTEXT)
