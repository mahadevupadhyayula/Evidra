import pytest

from ai.client import MockAIClient
from ai.services import AIStoryGenerationError, AIStoryScoringError, EvidraAIService
from tests.stories.helpers import generated_story, story_score


def test_generate_stories_retries_once_and_accepts_valid_retry():
    client = MockAIClient(
        responses=[
            {"stories": []},
            {"stories": [generated_story(1)]},
        ]
    )

    stories = EvidraAIService(client=client).generate_stories(
        approved_evidence=[{"id": 1, "title": "Evidence", "source_excerpt": "20% outcome"}],
        profile_context={},
    )

    assert len(stories.stories) == 1
    assert len([call for call in client.calls if call["operation"] == "generate_stories"]) == 2


def test_generate_stories_rejects_unknown_evidence_reference():
    client = MockAIClient(
        responses=[{"stories": [generated_story(99)]}, {"stories": [generated_story(99)]}]
    )

    with pytest.raises(AIStoryGenerationError):
        EvidraAIService(client=client).generate_stories(
            approved_evidence=[{"id": 1, "title": "Evidence", "source_excerpt": "outcome"}],
            profile_context={},
        )


def test_generate_stories_rejects_unsupported_numeric_claim():
    client = MockAIClient(
        responses=[
            {"stories": [generated_story(1, metric="99%")]},
            {"stories": [generated_story(1, metric="99%")]},
        ]
    )

    with pytest.raises(AIStoryGenerationError):
        EvidraAIService(client=client).generate_stories(
            approved_evidence=[{"id": 1, "title": "Evidence", "source_excerpt": "20% outcome"}],
            profile_context={},
        )


def test_score_stories_requires_score_for_each_story():
    client = MockAIClient(
        responses=[{"scores": [story_score("other")]}, {"scores": [story_score("other")]}]
    )

    with pytest.raises(AIStoryScoringError):
        EvidraAIService(client=client).score_stories(
            stories=[generated_story(1)],
            approved_evidence=[{"id": 1, "title": "Evidence"}],
        )
