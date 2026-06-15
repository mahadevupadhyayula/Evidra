from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.matching.models import StoryMatch
from apps.sprints.models import SprintState
from tests.matching.helpers import make_stories_ready_sprint, match_response


@pytest.mark.django_db
def test_matching_generate_view_creates_matches(client):
    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint()
    client.force_login(user)
    with patch("apps.matching.services.EvidraAIService.score_story_matches") as score:
        from ai.schemas.matching import StoryMatchSet

        score.return_value = StoryMatchSet.model_validate(match_response(story, evidence))
        response = client.post(reverse("matching:generate"))
    assert response.status_code == 302
    sprint.refresh_from_db()
    assert sprint.state == SprintState.MATCHING_READY
    assert StoryMatch.objects.filter(sprint=sprint).exists()


@pytest.mark.django_db
def test_matching_index_displays_gap(client):
    user, sprint, _profile, _evidence, _story, _alternative = make_stories_ready_sprint()
    sprint.state = SprintState.MATCHING_READY
    sprint.save(update_fields=["state", "updated_at"])
    StoryMatch.objects.create(
        sprint=sprint,
        competency_key="product_strategy",
        competency_label="Product strategy",
        missing_signal="Add a credible strategy story.",
    )
    client.force_login(user)
    response = client.get(reverse("matching:index"))
    assert response.status_code == 200
    assert b"Add a credible strategy story" in response.content


@pytest.mark.django_db
def test_matching_override_rejects_cross_user_match(client):
    user, sprint, _profile, _evidence, story, _alternative = make_stories_ready_sprint()
    sprint.state = SprintState.MATCHING_READY
    sprint.save(update_fields=["state", "updated_at"])
    match = StoryMatch.objects.create(
        sprint=sprint,
        competency_key="product_strategy",
        competency_label="Product strategy",
        primary_story=story,
        total_score=80,
    )
    other, _other_sprint, _profile, _evidence, _story, _alternative = make_stories_ready_sprint(
        "view-other@example.com"
    )
    client.force_login(other)
    response = client.post(
        reverse("matching:override", args=[match.id]), {"selected_story_id": story.id}
    )
    assert response.status_code == 302
    match.refresh_from_db()
    assert match.user_selected is False
