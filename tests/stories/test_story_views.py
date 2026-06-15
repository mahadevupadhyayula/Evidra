import pytest
from django.urls import reverse

from ai.schemas.stories import GeneratedStorySet, StoryScoreSet
from apps.evidence.models import EvidenceCard
from apps.sprints.models import InterviewSprint, SprintState
from apps.stories.models import Story
from tests.stories.helpers import generated_story, make_evidence_approved_sprint, story_score


@pytest.mark.django_db
def test_story_bank_requires_login(client):
    response = client.get(reverse("stories:story_bank"))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_story_bank_available_after_evidence_approval(client):
    user, _sprint, _profile = make_evidence_approved_sprint("view-stories@example.com")
    client.force_login(user)

    response = client.get(reverse("stories:story_bank"))

    assert response.status_code == 200
    assert b"Generate reusable stories" in response.content


@pytest.mark.django_db
def test_story_generate_view_uses_real_service_with_mocked_ai(client, monkeypatch):
    user, sprint, _profile = make_evidence_approved_sprint("generate-view@example.com")
    evidence = EvidenceCard.objects.filter(user=user).first()
    client.force_login(user)

    def fake_generate_stories(self, *, approved_evidence, profile_context):
        return GeneratedStorySet.model_validate({"stories": [generated_story(evidence.id)]})

    def fake_score_stories(self, *, stories, approved_evidence):
        return StoryScoreSet.model_validate({"scores": [story_score()]})

    monkeypatch.setattr(
        "apps.stories.services.EvidraAIService.generate_stories",
        fake_generate_stories,
    )
    monkeypatch.setattr(
        "apps.stories.services.EvidraAIService.score_stories",
        fake_score_stories,
    )

    response = client.post(reverse("stories:story_generate"))

    assert response.status_code == 302
    sprint.refresh_from_db()
    assert sprint.state == SprintState.STORIES_READY
    assert Story.objects.filter(user=user, title="Delivered outcomes").exists()


@pytest.mark.django_db
def test_story_edit_blocks_cross_user(client):
    user, _sprint, profile = make_evidence_approved_sprint("owner-view@example.com")
    other, _other_sprint, _other_profile = make_evidence_approved_sprint("other-view@example.com")
    evidence = EvidenceCard.objects.filter(user=user).first()
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Owned",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
    )
    client.force_login(other)

    response = client.get(reverse("stories:story_edit", args=[story.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_story_edit_invalid_sprint_state_redirects_safely(client):
    user, sprint, profile = make_evidence_approved_sprint("invalid-edit-state@example.com")
    evidence = EvidenceCard.objects.filter(user=user).first()
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Owned",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[evidence.id],
    )
    sprint.delete()
    InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)
    client.force_login(user)

    response = client.get(reverse("stories:story_edit", args=[story.id]))

    assert response.status_code == 302
    assert response.url == reverse("workspace:index")
