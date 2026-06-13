import pytest
from django.contrib.auth import get_user_model

from apps.sprints.models import InterviewSprint, SprintState


@pytest.mark.django_db
def test_interview_sprint_defaults_to_draft():
    user = get_user_model().objects.create_user(username="user@example.com")

    sprint = InterviewSprint.objects.create(user=user)

    assert sprint.state == SprintState.DRAFT
    assert sprint.completed_at is None


def test_sprint_states_match_approved_state_machine():
    assert [state.value for state in SprintState] == [
        "DRAFT",
        "RESUME_READY",
        "PROFILE_CONFIRMED",
        "OPPORTUNITY_CONFIRMED",
        "EVIDENCE_REVIEW",
        "EVIDENCE_APPROVED",
        "STORIES_READY",
        "MATCHING_READY",
        "PREVIEW_READY",
        "PAYMENT_PENDING",
        "PAID",
        "PREPKIT_READY",
        "PRACTICE_ACTIVE",
        "PLAN_READY",
        "COMPLETED",
    ]
