from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.documents.models import Document, DocumentParsingStatus
from apps.profiles.models import CareerProfile, CareerProfileStatus
from apps.sprints.models import InterviewSprint, SprintState


def resume_text():
    return "Experience leading product teams and delivering customer outcomes. " * 5


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
def test_profile_review_requires_login(client):
    response = client.get("/workspace/profile/review/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_profile_review_creates_blank_draft_without_ai(client):
    user = get_user_model().objects.create_user(username="user@example.com", password="password")
    _sprint, document = make_resume_ready_sprint(user)
    client.login(username="user@example.com", password="password")

    with patch("apps.profiles.services.EvidraAIService.extract_profile") as extract:
        response = client.get("/workspace/profile/review/")

    assert response.status_code == 200
    profile = CareerProfile.objects.get(user=user, active_resume=document)
    assert profile.full_name is None
    extract.assert_not_called()


@pytest.mark.django_db
def test_profile_generate_updates_draft_with_fake_ai(client):
    user = get_user_model().objects.create_user(
        username="generate@example.com",
        password="password",
    )
    _sprint, document = make_resume_ready_sprint(user)
    client.login(username="generate@example.com", password="password")

    with patch("apps.profiles.services.EvidraAIService.extract_profile") as extract:
        from ai.schemas.profile import ExtractedProfile

        extract.return_value = ExtractedProfile.model_validate(
            {
                "full_name": "Alex Candidate",
                "current_role": None,
                "current_company": None,
                "years_experience": 7,
                "industries": ["SaaS"],
                "functional_areas": ["Product"],
                "skills": ["Discovery"],
                "tools": ["Jira"],
                "education_summary": None,
                "career_summary": "Builds products.",
                "positioning_summary": "Product leader.",
                "uncertain_fields": [],
            }
        )
        response = client.post("/workspace/profile/generate/")

    assert response.status_code == 302
    profile = CareerProfile.objects.get(user=user, active_resume=document)
    assert profile.full_name == "Alex Candidate"
    extract.assert_called_once_with(document.cleaned_text)


@pytest.mark.django_db
def test_profile_save_updates_draft_without_transition(client):
    user = get_user_model().objects.create_user(username="user@example.com", password="password")
    sprint, document = make_resume_ready_sprint(user)
    profile = CareerProfile.objects.create(user=user, active_resume=document)
    client.login(username="user@example.com", password="password")

    response = client.post(
        f"/workspace/profile/{profile.pk}/save/",
        data={
            "full_name": "Alex Candidate",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": "7",
            "industries": "SaaS",
            "functional_areas": "Product",
            "skills": "Discovery",
            "tools": "Jira",
            "education_summary": "",
            "career_summary": "Builds products.",
            "positioning_summary": "Product leader.",
        },
    )

    assert response.status_code == 302
    profile.refresh_from_db()
    sprint.refresh_from_db()
    assert profile.full_name == "Alex Candidate"
    assert sprint.state == SprintState.RESUME_READY


@pytest.mark.django_db
def test_profile_confirm_transitions_sprint(client):
    user = get_user_model().objects.create_user(username="user@example.com", password="password")
    sprint, document = make_resume_ready_sprint(user)
    profile = CareerProfile.objects.create(user=user, active_resume=document)
    client.login(username="user@example.com", password="password")

    response = client.post(
        f"/workspace/profile/{profile.pk}/confirm/",
        data={
            "full_name": "Alex Candidate",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": "7",
            "industries": "SaaS",
            "functional_areas": "Product",
            "skills": "Discovery",
            "tools": "Jira",
            "education_summary": "",
            "career_summary": "Builds products.",
            "positioning_summary": "Product leader.",
        },
    )

    assert response.status_code == 302
    profile.refresh_from_db()
    sprint.refresh_from_db()
    assert profile.confirmation_status == CareerProfileStatus.CONFIRMED
    assert sprint.state == SprintState.PROFILE_CONFIRMED
    assert sprint.active_profile == profile


@pytest.mark.django_db
def test_profile_confirm_rejects_cross_user_profile(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com", password="password")
    other = User.objects.create_user(username="other@example.com", password="password")
    _sprint, document = make_resume_ready_sprint(owner)
    make_resume_ready_sprint(other)
    profile = CareerProfile.objects.create(user=owner, active_resume=document)
    client.login(username="other@example.com", password="password")

    response = client.post(f"/workspace/profile/{profile.pk}/confirm/", data={})

    assert response.status_code == 404


@pytest.mark.django_db
def test_profile_confirm_does_not_mutate_already_confirmed_profile(client):
    user = get_user_model().objects.create_user(username="done@example.com", password="password")
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
    client.login(username="done@example.com", password="password")

    response = client.post(
        f"/workspace/profile/{profile.pk}/confirm/",
        data={
            "full_name": "Changed Name",
            "current_role": "Product Manager",
            "current_company": "ExampleCo",
            "years_experience": "7",
            "industries": "SaaS",
            "functional_areas": "Product",
            "skills": "Discovery",
            "tools": "Jira",
            "education_summary": "",
            "career_summary": "Builds products.",
            "positioning_summary": "Product leader.",
        },
    )

    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.full_name == "Original Name"
