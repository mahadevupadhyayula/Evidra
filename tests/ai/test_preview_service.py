import pytest

from ai.client import MockAIClient
from ai.services import AIPreviewGenerationError, EvidraAIService
from tests.previews.helpers import preview_response


def test_generate_preview_retries_once_for_structural_failure():
    match = type("M", (), {"id": 1})()
    story = type("S", (), {"id": 2, "title": "Story", "short_answer": "Excerpt"})()
    evidence = type("E", (), {"id": 3})()
    client = MockAIClient(
        responses=[{"role_summary": "bad"}, preview_response(match, story, evidence)]
    )
    preview = EvidraAIService(client=client).generate_preview(
        opportunity_context={"role_title": "PM"},
        role_pack={"key": "PRODUCT_MANAGEMENT"},
        matches=[{"id": 1, "competency_key": "product_strategy"}],
        stories=[{"id": 2}],
        approved_evidence=[{"id": 3}],
        matched_story_excerpt_source={
            "story_id": 2,
            "match_id": 1,
            "title": "Story",
            "excerpt": "Excerpt",
            "evidence_ids": [3],
        },
        deterministic_counts={
            "approved_evidence_count": 1,
            "result_backed_evidence_count": 1,
            "competencies_with_evidence_count": 1,
            "ready_story_count": 1,
            "matched_competency_count": 1,
            "gap_competency_count": 0,
        },
    )
    assert preview.role_summary.startswith("This role")
    assert len(client.calls) == 2


def test_generate_preview_rejects_invalid_output_after_retry():
    client = MockAIClient(responses=[{"role_summary": "bad"}, {"role_summary": "bad"}])
    with pytest.raises(AIPreviewGenerationError):
        EvidraAIService(client=client).generate_preview(
            opportunity_context={"role_title": "PM"},
            role_pack={"key": "PRODUCT_MANAGEMENT"},
            matches=[{"id": 1}],
            stories=[{"id": 2}],
            approved_evidence=[{"id": 3}],
            matched_story_excerpt_source={
                "story_id": 2,
                "match_id": 1,
                "title": "Story",
                "excerpt": "Excerpt",
                "evidence_ids": [3],
            },
            deterministic_counts={},
        )
