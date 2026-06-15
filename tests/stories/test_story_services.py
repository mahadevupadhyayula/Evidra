import pytest
from django.http import Http404

from ai.client import MockAIClient
from ai.services import AIStoryGenerationError, EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.sprints.models import SprintState
from apps.sprints.services import InvalidSprintTransition
from apps.stories.models import Story, StoryGenerationFailure, StoryStatus
from apps.stories.services import StoryError, StoryService
from tests.stories.helpers import generated_story, make_evidence_approved_sprint, story_score


@pytest.mark.django_db
def test_generate_stories_creates_ready_story_and_transitions():
    user, sprint, _profile = make_evidence_approved_sprint()
    evidence = EvidenceCard.objects.filter(user=user, status=EvidenceStatus.APPROVED).first()
    client = MockAIClient(
        responses=[
            {"stories": [generated_story(evidence.id)]},
            {"scores": [story_score()]},
        ]
    )

    stories = StoryService.generate_stories(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=client),
    )

    sprint.refresh_from_db()
    story = stories[0]
    assert sprint.state == SprintState.STORIES_READY
    assert story.status == StoryStatus.READY
    assert story.quality_score == 80
    assert story.evidence_ids == [evidence.id]


@pytest.mark.django_db
def test_generate_stories_is_idempotent_without_regenerate():
    user, sprint, profile = make_evidence_approved_sprint()
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Existing",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[EvidenceCard.objects.filter(user=user).first().id],
        status=StoryStatus.READY,
    )

    stories = StoryService.generate_stories(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=MockAIClient()),
    )

    assert stories == [story]
    assert Story.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_save_story_marks_edited_and_preserves_ownership():
    user, sprint, profile = make_evidence_approved_sprint()
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    evidence = EvidenceCard.objects.filter(user=user).first()
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Original",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
        status=StoryStatus.READY,
    )

    saved = StoryService.save_story(
        user=user,
        sprint=sprint,
        story_id=story.id,
        cleaned_data={
            "title": "Edited",
            "story_type": "IMPACT",
            "situation": "Situation",
            "task": "Task",
            "action": "Action",
            "result": "Result",
            "learning": "Learning",
            "short_answer": "Edited short",
            "ninety_second_answer": "Edited medium",
            "detailed_answer": "Edited detailed",
            "competency_tags_text": ["Execution"],
            "seniority_signals_text": ["Ownership"],
            "missing_details_text": [],
            "evidence_ids": [evidence.id],
        },
    )

    assert saved.status == StoryStatus.EDITED
    assert saved.title == "Edited"
    assert saved.user_edited_data["edited"] is True


@pytest.mark.django_db
def test_regenerate_story_creates_draft_revision_without_overwriting_source():
    user, sprint, profile = make_evidence_approved_sprint()
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    evidence = EvidenceCard.objects.filter(user=user).first()
    source = Story.objects.create(
        user=user,
        profile=profile,
        title="Edited source",
        short_answer="User edited short",
        ninety_second_answer="User edited medium",
        detailed_answer="User edited detailed",
        evidence_ids=[evidence.id],
        status=StoryStatus.EDITED,
        user_edited_data={"edited": True},
    )
    client = MockAIClient(
        responses=[
            {"stories": [generated_story(evidence.id)]},
            {"scores": [story_score()]},
        ]
    )

    revision = StoryService.regenerate_story(
        user=user,
        sprint=sprint,
        story_id=source.id,
        ai_service=EvidraAIService(client=client),
    )

    source.refresh_from_db()
    assert source.short_answer == "User edited short"
    assert revision.source_story == source
    assert revision.status == StoryStatus.DRAFT
    assert revision.revision_number == 2


@pytest.mark.django_db
def test_story_service_blocks_cross_user_story_access():
    user, sprint, profile = make_evidence_approved_sprint()
    other, other_sprint, _other_profile = make_evidence_approved_sprint("other-stories@example.com")
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Owned",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[EvidenceCard.objects.filter(user=user).first().id],
    )

    with pytest.raises(Http404):
        StoryService.get_owned_story(user=other, sprint=other_sprint, story_id=story.id)


@pytest.mark.django_db
def test_generate_stories_rejects_unapproved_evidence_reference():
    user, sprint, _profile = make_evidence_approved_sprint()
    draft = EvidenceCard.objects.create(
        user=user,
        profile=sprint.active_profile,
        source_document=sprint.active_resume,
        title="Draft evidence",
        source_excerpt="Experience leading product teams and delivering customer outcomes.",
        status=EvidenceStatus.DRAFT,
    )
    client = MockAIClient(
        responses=[
            {"stories": [generated_story(draft.id)]},
            {"stories": [generated_story(draft.id)]},
        ]
    )

    with pytest.raises(AIStoryGenerationError):
        StoryService.generate_stories(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=client),
        )
    assert Story.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_save_story_rejects_unsupported_metric():
    user, sprint, profile = make_evidence_approved_sprint()
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    evidence = EvidenceCard.objects.filter(user=user).first()
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Original",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
    )

    with pytest.raises(StoryError):
        StoryService.save_story(
            user=user,
            sprint=sprint,
            story_id=story.id,
            cleaned_data={
                "title": "Edited",
                "story_type": "IMPACT",
                "situation": "Situation",
                "task": "Task",
                "action": "Action",
                "result": "Improved by 99%",
                "learning": "Learning",
                "short_answer": "Improved by 99%",
                "ninety_second_answer": "Improved by 99%",
                "detailed_answer": "Improved by 99%",
                "competency_tags_text": [],
                "seniority_signals_text": [],
                "missing_details_text": [],
                "evidence_ids": [evidence.id],
            },
        )


@pytest.mark.django_db
def test_generate_stories_records_ai_failure_without_losing_existing_stories():
    user, sprint, profile = make_evidence_approved_sprint("story-failure@example.com")
    evidence = EvidenceCard.objects.filter(user=user).first()
    existing = Story.objects.create(
        user=user,
        profile=profile,
        title="Existing",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
        status=StoryStatus.READY,
    )
    Story.objects.filter(pk=existing.pk).update(status=StoryStatus.ARCHIVED)
    client = MockAIClient(responses=[{"stories": []}, {"stories": []}])

    with pytest.raises(AIStoryGenerationError):
        StoryService.generate_stories(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=client),
        )

    existing.refresh_from_db()
    failure = StoryGenerationFailure.objects.get(user=user, profile=profile)
    assert existing.title == "Existing"
    assert failure.operation == "generate"
    assert "invalid structured output" in failure.error_message


@pytest.mark.django_db
def test_list_stories_attaches_approved_evidence_references():
    user, sprint, profile = make_evidence_approved_sprint("story-references@example.com")
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    evidence = EvidenceCard.objects.filter(user=user).first()
    Story.objects.create(
        user=user,
        profile=profile,
        title="Referenced",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
        status=StoryStatus.READY,
    )

    story = StoryService.list_stories(user=user, sprint=sprint)[0]

    assert story.evidence_references == [evidence]


@pytest.mark.django_db
def test_generate_stories_requires_evidence_approved_state():
    user, sprint, _profile = make_evidence_approved_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(InvalidSprintTransition):
        StoryService.generate_stories(user=user, sprint=sprint)
