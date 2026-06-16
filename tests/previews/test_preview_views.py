import pytest
from django.urls import reverse

from apps.generations.models import GenerationRun, GenerationRunStatus
from apps.previews.models import ReadinessPreview
from apps.sprints.models import SprintState
from tests.previews.helpers import make_matching_ready_sprint


@pytest.mark.django_db
def test_preview_generate_view_queues_preview_generation(client):
    user, sprint, *_rest = make_matching_ready_sprint()
    client.force_login(user)

    response = client.post(reverse("previews:generate"))

    assert response.status_code == 302
    sprint.refresh_from_db()
    assert sprint.state == SprintState.MATCHING_READY
    assert GenerationRun.objects.filter(
        sprint=sprint, status=GenerationRunStatus.PENDING
    ).exists()


@pytest.mark.django_db
def test_preview_detail_displays_sections_and_placeholder(client):
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    ReadinessPreview.objects.create(
        sprint=sprint,
        role_summary="This role emphasizes product strategy.",
        competencies=[{"label": "Product strategy", "readiness": "covered"}],
        strengths=[{"title": "Evidence-backed", "explanation": "Grounded in approved evidence."}],
        gaps=[{"title": "Practice", "explanation": "Needs interview-specific polish."}],
        evidence_completeness={
            "approved_evidence_count": 1,
            "result_backed_evidence_count": 1,
            "competencies_with_evidence_count": 1,
            "summary": "Evidence summary",
        },
        story_coverage={
            "ready_story_count": 1,
            "matched_competency_count": 1,
            "gap_competency_count": 0,
            "summary": "Story summary",
        },
        matched_story_excerpt={
            "story_id": story.id,
            "match_id": match.id,
            "title": story.title,
            "excerpt": story.short_answer,
            "evidence_ids": [evidence.id],
        },
        prepkit_explanation="The paid Prep Kit will expand this preview.",
        input_revision="abc",
        status="READY",
    )
    sprint.state = SprintState.PREVIEW_READY
    sprint.save(update_fields=["state", "updated_at"])
    client.force_login(user)
    response = client.get(reverse("previews:detail"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Role summary" in content
    assert "Create Razorpay order" in content
    assert "offer probability" not in content.casefold()


@pytest.mark.django_db
def test_preview_detail_before_matching_redirects(client):
    user, sprint, *_rest = make_matching_ready_sprint()
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    client.force_login(user)
    response = client.get(reverse("previews:detail"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_user_owned_pages_remain_visible_after_preview_ready(client):
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    ReadinessPreview.objects.create(
        sprint=sprint,
        role_summary="This role emphasizes product strategy.",
        competencies=[
            {"key": f"competency_{index}", "label": f"Competency {index}", "readiness": "covered"}
            for index in range(5)
        ],
        strengths=[
            {"title": f"Strength {index}", "explanation": "Grounded in approved evidence."}
            for index in range(3)
        ],
        gaps=[
            {"title": f"Gap {index}", "explanation": "Needs interview-specific polish."}
            for index in range(3)
        ],
        evidence_completeness={
            "approved_evidence_count": 1,
            "result_backed_evidence_count": 1,
            "competencies_with_evidence_count": 1,
            "summary": "Evidence summary",
        },
        story_coverage={
            "ready_story_count": 1,
            "matched_competency_count": 1,
            "gap_competency_count": 0,
            "summary": "Story summary",
        },
        matched_story_excerpt={
            "story_id": story.id,
            "match_id": match.id,
            "title": story.title,
            "excerpt": story.short_answer,
            "evidence_ids": [evidence.id],
        },
        prepkit_explanation="The paid Prep Kit will expand this preview.",
        input_revision="abc",
        status="READY",
    )
    sprint.state = SprintState.PREVIEW_READY
    sprint.save(update_fields=["state", "updated_at"])
    client.force_login(user)

    for route_name in [
        "profiles:profile_review",
        "evidence:evidence_review",
        "stories:story_bank",
        "matching:index",
    ]:
        response = client.get(reverse(route_name))
        assert response.status_code == 200, route_name
