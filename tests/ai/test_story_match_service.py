import pytest

from ai.client import MockAIClient
from ai.services import AIStoryMatchScoringError, EvidraAIService
from tests.matching.helpers import match_response


def test_score_story_matches_retries_once_for_structural_failure():
    client = MockAIClient(
        responses=[
            {"matches": []},
            match_response(type("S", (), {"id": 1})(), type("E", (), {"id": 1})()),
        ]
    )
    matches = EvidraAIService(client=client).score_story_matches(
        opportunity_context={"job_description": "Lead product strategy"},
        role_pack={"key": "PRODUCT_MANAGEMENT"},
        competency_map=[{"key": "product_strategy", "label": "Product strategy"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
    )
    assert matches.matches[0].primary_story_id == 1
    assert len(client.calls) == 2


def test_score_story_matches_rejects_unknown_story_id():
    client = MockAIClient(
        responses=[
            match_response(type("S", (), {"id": 99})(), type("E", (), {"id": 1})()),
            match_response(type("S", (), {"id": 99})(), type("E", (), {"id": 1})()),
        ]
    )
    with pytest.raises(AIStoryMatchScoringError):
        EvidraAIService(client=client).score_story_matches(
            opportunity_context={"job_description": "Lead product strategy"},
            role_pack={"key": "PRODUCT_MANAGEMENT"},
            competency_map=[{"key": "product_strategy", "label": "Product strategy"}],
            stories=[{"id": 1}],
            approved_evidence=[{"id": 1}],
        )


def test_score_story_matches_rejects_unsupported_numeric_claim():
    response = match_response(type("S", (), {"id": 1})(), type("E", (), {"id": 1})())
    response["matches"][0]["explanation"] = "This story improved revenue by 42%."
    client = MockAIClient(responses=[response, response])
    with pytest.raises(AIStoryMatchScoringError):
        EvidraAIService(client=client).score_story_matches(
            opportunity_context={"job_description": "Lead product strategy"},
            role_pack={"key": "PRODUCT_MANAGEMENT"},
            competency_map=[{"key": "product_strategy", "label": "Product strategy"}],
            stories=[{"id": 1, "short_answer": "Led strategy"}],
            approved_evidence=[{"id": 1, "source_excerpt": "Led strategy"}],
        )
