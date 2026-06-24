import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.sprints.models import InterviewSprint, SprintState


@pytest.mark.django_db
def test_workspace_requires_authentication(client):
    response = client.get(reverse("workspace:index"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_workspace_create_current_sprint(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)

    response = client.post(reverse("workspace:current_sprint"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:index")
    sprint = InterviewSprint.objects.get(user=user)
    assert sprint.state == SprintState.DRAFT


@pytest.mark.django_db
def test_workspace_create_current_sprint_is_idempotent(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)

    client.post(reverse("workspace:current_sprint"))
    client.post(reverse("workspace:current_sprint"))

    assert InterviewSprint.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_workspace_only_displays_authenticated_users_sprint(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    viewer = User.objects.create_user(username="viewer@example.com")
    other_sprint = InterviewSprint.objects.create(user=owner)
    client.force_login(viewer)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert b"Sprint ID" not in response.content
    assert (
        f"Sprint ID</dt>\n    <dd>{other_sprint.pk}</dd>".encode() not in response.content
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "label", "url_name"),
    [
        (SprintState.DRAFT, "Add resume", "documents:resume_upload"),
        (SprintState.RESUME_READY, "Review profile", "profiles:profile_review"),
        (
            SprintState.PROFILE_CONFIRMED,
            "Add opportunity context",
            "opportunities:opportunity_detail",
        ),
        (SprintState.OPPORTUNITY_CONFIRMED, "Review evidence", "evidence:evidence_review"),
        (SprintState.EVIDENCE_REVIEW, "Review evidence", "evidence:evidence_review"),
        (SprintState.EVIDENCE_APPROVED, "Generate reusable stories", "stories:story_bank"),
        (SprintState.STORIES_READY, "Review story bank", "stories:story_bank"),
        (SprintState.MATCHING_READY, "Review readiness preview", "previews:detail"),
        (SprintState.PREVIEW_READY, "Review readiness preview", "previews:detail"),
        (SprintState.PAYMENT_PENDING, "Open Prep Kit", "prepkits:detail"),
        (SprintState.PAID, "Open Prep Kit", "prepkits:detail"),
        (SprintState.PREPKIT_READY, "Practice answers", "practice:index"),
        (SprintState.PRACTICE_ACTIVE, "Open seven-day plan", "plans:detail"),
        (SprintState.PLAN_READY, "Open seven-day plan", "plans:detail"),
    ],
)
def test_workspace_next_step_uses_link_for_navigation_ctas(client, state, label, url_name):
    user = get_user_model().objects.create_user(username=f"{state}@example.com")
    InterviewSprint.objects.create(user=user, state=state)
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    expected_link = f'<a class="button-link" href="{reverse(url_name)}">{label}</a>'
    assert expected_link.encode() in response.content
    assert b'<form method="post" action="/workspace/sprints/current/">' not in response.content


@pytest.mark.django_db
def test_workspace_next_step_uses_post_form_to_create_sprint(client):
    user = get_user_model().objects.create_user(username="starter@example.com")
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert b"Create Interview Sprint" in response.content
    assert (
        f'<form method="post" action="{reverse("workspace:current_sprint")}">'.encode()
        in response.content
    )
    assert b"Your data is private and secure." in response.content
