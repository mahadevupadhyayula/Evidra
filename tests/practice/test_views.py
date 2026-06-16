import pytest
from django.urls import reverse

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.practice.models import PracticeAttempt
from apps.sprints.models import SprintState
from tests.practice.helpers import make_practice_ready_sprint


@pytest.mark.django_db
def test_practice_index_requires_login(client):
    response = client.get(reverse("practice:index"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_practice_index_shows_questions_for_ready_prepkit(client):
    user, _sprint, _prepkit = make_practice_ready_sprint()
    client.force_login(user)

    response = client.get(reverse("practice:index"))

    assert response.status_code == 200
    assert b"Tell me about the approved story" in response.content


@pytest.mark.django_db
def test_practice_submit_creates_attempt(client, monkeypatch):
    user, sprint, _prepkit = make_practice_ready_sprint()
    client.force_login(user)
    monkeypatch.setattr(
        "apps.practice.services.EvidraAIService",
        lambda: EvidraAIService(client=MockAIClient()),
    )

    response = client.post(
        reverse("practice:submit"),
        {
            "question_id": "q1",
            "answer_text": "I led the approved work and explained the result clearly.",
        },
    )

    assert response.status_code == 302
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 1
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PRACTICE_ACTIVE

    response = client.get(reverse("practice:index"))
    assert response.status_code == 200
    assert b"Tell me about the approved story" in response.content

    response = client.post(
        reverse("practice:submit"),
        {
            "question_id": "q1",
            "answer_text": "I led the approved work and explained the result clearly again.",
        },
    )
    assert response.status_code == 302
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 2

    response = client.get(reverse("practice:index"))
    content = response.content.decode()
    assert "Comparison:" in content
    assert "Your answer:" in content
    assert "I led the approved work and explained the result clearly." in content


@pytest.mark.django_db
def test_practice_submit_invalid_answer_does_not_create_attempt(client):
    user, sprint, _prepkit = make_practice_ready_sprint()
    client.force_login(user)

    response = client.post(
        reverse("practice:submit"), {"question_id": "q1", "answer_text": "short"}
    )

    assert response.status_code == 200
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0
