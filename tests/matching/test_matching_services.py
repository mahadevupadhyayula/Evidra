import pytest
from django.http import Http404

from ai.client import AIClientError, MockAIClient
from ai.services import AIStoryMatchScoringError, EvidraAIService
from apps.matching.models import StoryMatch
from apps.matching.services import MatchingService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from tests.matching.helpers import make_stories_ready_sprint, match_response
from tests.opportunities.helpers import make_profile_confirmed_sprint


@pytest.mark.django_db
def test_generate_matches_creates_rows_and_transitions():
    user, sprint, _profile, evidence, story, alternative = make_stories_ready_sprint()
    response = match_response(story, evidence, alternative=alternative)
    matches = MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.MATCHING_READY
    match = next(item for item in matches if item.competency_key == "product_strategy")
    assert match.primary_story == story
    assert match.alternative_story == alternative
    assert match.total_score == 80


@pytest.mark.django_db
def test_generate_matches_is_idempotent_without_force():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    ai_client = MockAIClient(responses=[match_response(story, evidence)])
    MatchingService.generate_matches(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=ai_client)
    )
    first_count = StoryMatch.objects.count()
    sprint.refresh_from_db()
    MatchingService.generate_matches(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=ai_client)
    )
    assert StoryMatch.objects.count() == first_count
    assert len(ai_client.calls) == 1


@pytest.mark.django_db
def test_low_score_creates_explicit_gap():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    response = match_response(story, evidence, score=35)
    matches = MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
    )
    assert matches[0].primary_story is None
    assert matches[0].total_score == 0
    assert matches[0].missing_signal


@pytest.mark.django_db
def test_ai_failure_preserves_existing_matches():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(responses=[match_response(story, evidence)])
        ),
    )
    sprint.refresh_from_db()
    with pytest.raises(AIStoryMatchScoringError):
        MatchingService.generate_matches(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("boom"), AIClientError("boom")])
            ),
            force=True,
        )
    assert StoryMatch.objects.filter(sprint=sprint).count() > 0


@pytest.mark.django_db
def test_set_user_override_records_selected_story_without_changing_scores():
    user, sprint, _profile, evidence, story, alternative = make_stories_ready_sprint()
    matches = MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(
                responses=[match_response(story, evidence, alternative=alternative)]
            )
        ),
    )
    sprint.refresh_from_db()
    match = next(item for item in matches if item.competency_key == "product_strategy")
    updated = MatchingService.set_user_override(
        user=user,
        sprint=sprint,
        match_id=match.id,
        story_id=alternative.id,
    )
    assert updated.user_selected is True
    assert updated.selected_story_id == alternative.id
    assert updated.primary_story_id == story.id
    assert updated.total_score == 80


@pytest.mark.django_db
def test_set_user_override_rejects_cross_user_match():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    match = MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(responses=[match_response(story, evidence)])
        ),
    )[0]
    other, other_sprint, _profile = make_profile_confirmed_sprint("other-match@example.com")
    other_sprint.state = SprintState.MATCHING_READY
    other_sprint.save(update_fields=["state", "updated_at"])
    with pytest.raises(Http404):
        MatchingService.set_user_override(
            user=other,
            sprint=other_sprint,
            match_id=match.id,
            story_id=story.id,
        )


@pytest.mark.django_db
def test_generate_matches_requires_stories_ready():
    user, sprint, _profile = make_profile_confirmed_sprint("not-ready@example.com")
    with pytest.raises(InvalidSprintTransition):
        MatchingService.generate_matches(user=user, sprint=sprint)


@pytest.mark.django_db
def test_generate_matches_filters_evidence_ids_to_primary_story_evidence():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    from apps.evidence.models import EvidenceCard, EvidenceStatus

    unrelated = EvidenceCard.objects.create(
        user=user,
        profile=sprint.active_profile,
        source_document=sprint.active_resume,
        title="Unrelated approved evidence",
        action="Did unrelated work",
        source_excerpt="Did unrelated work",
        source_location="resume",
        status=EvidenceStatus.APPROVED,
    )
    response = match_response(story, evidence)
    response["matches"][0]["evidence_ids"] = [evidence.id, unrelated.id]
    match = next(
        item
        for item in MatchingService.generate_matches(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
        if item.competency_key == "product_strategy"
    )
    assert match.evidence_ids == [evidence.id]


@pytest.mark.django_db
def test_generate_matches_rejects_numeric_claim_from_unrelated_evidence():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.matching.services import MatchingError

    unrelated = EvidenceCard.objects.create(
        user=user,
        profile=sprint.active_profile,
        source_document=sprint.active_resume,
        title="Unrelated metric evidence",
        action="Did unrelated work",
        result="Improved conversion by 42%",
        source_excerpt="Improved conversion by 42%",
        source_location="resume",
        status=EvidenceStatus.APPROVED,
    )
    response = match_response(story, evidence)
    response["matches"][0]["evidence_ids"] = [evidence.id, unrelated.id]
    response["matches"][0]["explanation"] = "This story improved conversion by 42%."
    with pytest.raises(MatchingError):
        MatchingService.generate_matches(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert StoryMatch.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_story_edit_invalidates_existing_matches():
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(
            client=MockAIClient(responses=[match_response(story, evidence)])
        ),
    )
    sprint.refresh_from_db()
    from apps.stories.services import StoryService

    StoryService.save_story(
        user=user,
        sprint=sprint,
        story_id=story.id,
        cleaned_data={
            "title": story.title,
            "story_type": story.story_type,
            "situation": story.situation,
            "task": story.task,
            "action": story.action,
            "result": story.result,
            "learning": story.learning,
            "short_answer": story.short_answer,
            "ninety_second_answer": story.ninety_second_answer,
            "detailed_answer": story.detailed_answer,
            "competency_tags_text": story.competency_tags,
            "seniority_signals_text": story.seniority_signals,
            "missing_details_text": [],
            "evidence_ids": story.evidence_ids,
        },
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.STORIES_READY
    assert StoryMatch.objects.filter(sprint=sprint).count() == 0


def test_calculate_total_score_uses_python_weights():
    assert (
        MatchingService.calculate_total_score(
            competency_score=100,
            role_relevance_score=80,
            seniority_score=60,
            evidence_strength_score=40,
            company_context_score=20,
        )
        == 69
    )


@pytest.mark.django_db
def test_mark_matching_ready_requires_matches_or_gaps():
    user, sprint, _profile, _evidence, _story, _alternative = make_stories_ready_sprint()
    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_matching_ready(
            user=user,
            sprint=sprint,
            has_matches_or_gaps=False,
        )
