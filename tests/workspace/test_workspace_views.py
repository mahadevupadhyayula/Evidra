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
    assert f">{other_sprint.pk}<".encode() not in response.content
