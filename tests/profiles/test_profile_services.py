import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import Http404

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.documents.models import Document, DocumentParsingStatus
from apps.profiles.models import CareerProfile, CareerProfileStatus, ProfileExtractionStatus
from apps.profiles.services import CareerProfileError, CareerProfileService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def resume_text():
    return "Experience leading product teams and delivering customer outcomes. " * 5


def ai_response():
    return {
        "full_name": "Alex Candidate",
        "current_role": None,
        "current_company": None,
        "years_experience": 7,
        "industries": ["SaaS"],
        "functional_areas": ["Product Management"],
        "skills": ["Discovery"],
        "tools": ["Jira"],
        "education_summary": None,
        "career_summary": "Product manager with B2B SaaS experience.",
        "positioning_summary": "Customer-focused product leader.",
        "uncertain_fields": [],
    }


def make_resume_ready_sprint(user):
    document = Document.objects.create(
        user=user,
        cleaned_text=resume_text(),
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )
    sprint = InterviewSprint.objects.create(
        user=user,
        state=SprintState.RESUME_READY,
        active_resume=document,
    )
    return sprint, document


@pytest.mark.django_db
def test_ensure_draft_profile_uses_confirmed_resume_text_only():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint, document = make_resume_ready_sprint(user)
    client = MockAIClient(responses=[ai_response()])

    profile = CareerProfileService.ensure_draft_profile(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=client),
    )

    assert profile.user == user
    assert profile.active_resume == document
    assert profile.confirmation_status == CareerProfileStatus.DRAFT
    assert profile.full_name == "Alex Candidate"
    assert profile.extraction_status == ProfileExtractionStatus.SUCCEEDED
    assert client.calls[0]["resume_text"] == document.cleaned_text.strip()


@pytest.mark.django_db
def test_ensure_draft_profile_is_idempotent_for_existing_draft():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint, document = make_resume_ready_sprint(user)
    existing = CareerProfile.objects.create(
        user=user,
        active_resume=document,
        full_name="Existing",
        extraction_status=ProfileExtractionStatus.SUCCEEDED,
    )
    client = MockAIClient(responses=[ai_response()])

    profile = CareerProfileService.ensure_draft_profile(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=client),
    )

    assert profile == existing
    assert client.calls == []
    assert CareerProfile.objects.filter(user=user, active_resume=document).count() == 1


@pytest.mark.django_db
def test_ensure_draft_profile_rejects_sprint_not_resume_ready():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(InvalidSprintTransition):
        CareerProfileService.ensure_draft_profile(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_get_owned_profile_rejects_cross_user_access():
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    other = User.objects.create_user(username="other@example.com")
    _sprint, document = make_resume_ready_sprint(owner)
    profile = CareerProfile.objects.create(user=owner, active_resume=document)

    with pytest.raises(Http404):
        CareerProfileService.get_owned_profile(other, profile.pk)


@pytest.mark.django_db
def test_update_profile_rejects_confirmed_profile():
    user = get_user_model().objects.create_user(username="user@example.com")
    _sprint, document = make_resume_ready_sprint(user)
    profile = CareerProfile.objects.create(
        user=user,
        active_resume=document,
        confirmation_status=CareerProfileStatus.CONFIRMED,
    )

    with pytest.raises(CareerProfileError):
        CareerProfileService.update_profile(user=user, profile_id=profile.pk, cleaned_data={})


@pytest.mark.django_db
def test_confirm_profile_transitions_sprint_to_profile_confirmed():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint, document = make_resume_ready_sprint(user)
    profile = CareerProfile.objects.create(user=user, active_resume=document)

    CareerProfileService.confirm_profile(
        user=user,
        sprint=sprint,
        profile_id=profile.pk,
        cleaned_data={
            "full_name": "Alex Candidate",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": 7,
            "industries": ["SaaS"],
            "functional_areas": ["Product"],
            "skills": ["Discovery"],
            "tools": ["Jira"],
            "education_summary": None,
            "career_summary": "Builds products.",
            "positioning_summary": "Product leader.",
        },
    )

    profile.refresh_from_db()
    sprint.refresh_from_db()
    assert profile.confirmation_status == CareerProfileStatus.CONFIRMED
    assert profile.confirmed_at is not None
    assert sprint.state == SprintState.PROFILE_CONFIRMED
    assert sprint.active_profile == profile


@pytest.mark.django_db
def test_mark_profile_confirmed_rejects_profile_for_different_resume():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint, _document = make_resume_ready_sprint(user)
    other_document = Document.objects.create(
        user=user,
        cleaned_text=resume_text(),
        parsing_status=DocumentParsingStatus.CONFIRMED,
    )
    profile = CareerProfile.objects.create(
        user=user,
        active_resume=other_document,
        confirmation_status=CareerProfileStatus.CONFIRMED,
    )

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_profile_confirmed(user=user, sprint=sprint, profile=profile)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.RESUME_READY


@pytest.mark.django_db
def test_confirm_profile_does_not_mutate_already_confirmed_profile():
    user = get_user_model().objects.create_user(username="confirmed@example.com")
    sprint, document = make_resume_ready_sprint(user)
    profile = CareerProfile.objects.create(
        user=user,
        active_resume=document,
        full_name="Original Name",
        confirmation_status=CareerProfileStatus.CONFIRMED,
    )
    sprint.state = SprintState.PROFILE_CONFIRMED
    sprint.active_profile = profile
    sprint.save(update_fields=["state", "active_profile", "updated_at"])

    CareerProfileService.confirm_profile(
        user=user,
        sprint=sprint,
        profile_id=profile.pk,
        cleaned_data={"full_name": "Changed Name"},
    )

    profile.refresh_from_db()
    assert profile.full_name == "Original Name"


@pytest.mark.django_db
def test_database_prevents_duplicate_current_profiles_for_resume():
    user = get_user_model().objects.create_user(username="unique@example.com")
    _sprint, document = make_resume_ready_sprint(user)
    CareerProfile.objects.create(user=user, active_resume=document)

    with pytest.raises(IntegrityError):
        CareerProfile.objects.create(user=user, active_resume=document)
