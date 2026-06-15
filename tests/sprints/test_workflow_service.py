import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import Http404

from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


@pytest.mark.django_db
def test_get_or_create_current_sprint_is_idempotent_for_user():
    user = get_user_model().objects.create_user(username="user@example.com")

    first = SprintWorkflowService.get_or_create_current_sprint(user)
    second = SprintWorkflowService.get_or_create_current_sprint(user)

    assert first.pk == second.pk
    assert InterviewSprint.objects.filter(user=user).count() == 1
    assert first.state == SprintState.DRAFT


@pytest.mark.django_db
def test_get_or_create_current_sprint_is_scoped_by_user():
    User = get_user_model()
    user_a = User.objects.create_user(username="a@example.com")
    user_b = User.objects.create_user(username="b@example.com")

    sprint_a = SprintWorkflowService.get_or_create_current_sprint(user_a)
    sprint_b = SprintWorkflowService.get_or_create_current_sprint(user_b)

    assert sprint_a.pk != sprint_b.pk
    assert sprint_a.user == user_a
    assert sprint_b.user == user_b


@pytest.mark.django_db
def test_database_prevents_duplicate_current_sprints_for_user():
    user = get_user_model().objects.create_user(username="user@example.com")

    InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(IntegrityError):
        InterviewSprint.objects.create(user=user, state=SprintState.RESUME_READY)


@pytest.mark.django_db
def test_user_can_have_completed_sprint_and_one_current_sprint():
    user = get_user_model().objects.create_user(username="user@example.com")
    InterviewSprint.objects.create(user=user, state=SprintState.COMPLETED)

    current = SprintWorkflowService.get_or_create_current_sprint(user)

    assert current.state == SprintState.DRAFT
    assert InterviewSprint.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_get_owned_sprint_rejects_cross_user_access():
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    other = User.objects.create_user(username="other@example.com")
    sprint = InterviewSprint.objects.create(user=owner)

    with pytest.raises(Http404):
        SprintWorkflowService.get_owned_sprint(other, sprint.pk)


@pytest.mark.django_db
def test_transition_fails_closed_without_stage_specific_condition_validation():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.transition(
            user=user,
            sprint=sprint,
            to_state=SprintState.RESUME_READY,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.DRAFT


@pytest.mark.django_db
def test_payment_transition_fails_closed_without_verified_payment_service():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.PAYMENT_PENDING)

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.transition(
            user=user,
            sprint=sprint,
            to_state=SprintState.PAID,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING


@pytest.mark.django_db
def test_transition_rejects_skip_and_preserves_state():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(InvalidSprintTransition):
        SprintWorkflowService.transition(
            user=user,
            sprint=sprint,
            to_state=SprintState.PROFILE_CONFIRMED,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.DRAFT


@pytest.mark.django_db
def test_transition_rejects_cross_user_mutation():
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    other = User.objects.create_user(username="other@example.com")
    sprint = InterviewSprint.objects.create(user=owner)

    with pytest.raises(SprintOwnershipError):
        SprintWorkflowService.transition(
            user=other,
            sprint=sprint,
            to_state=SprintState.RESUME_READY,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.DRAFT


@pytest.mark.django_db
def test_mark_opportunity_confirmed_rejects_unconfirmed_opportunity():
    from apps.opportunities.models import Opportunity
    from tests.opportunities.helpers import make_profile_confirmed_sprint, opportunity_data

    user, sprint, _profile = make_profile_confirmed_sprint("opportunity-transition@example.com")
    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_opportunity_confirmed(
            user=user,
            sprint=sprint,
            opportunity=opportunity,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_generic_transition_still_fails_closed_for_opportunity_confirmed():
    user = get_user_model().objects.create_user(username="generic-opportunity@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.PROFILE_CONFIRMED)

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.transition(
            user=user,
            sprint=sprint,
            to_state=SprintState.OPPORTUNITY_CONFIRMED,
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_mark_stories_ready_transitions_from_evidence_approved():
    user = get_user_model().objects.create_user(username="stories-ready@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.EVIDENCE_APPROVED)

    SprintWorkflowService.mark_stories_ready(user=user, sprint=sprint, has_usable_stories=True)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.STORIES_READY


@pytest.mark.django_db
def test_mark_stories_ready_requires_usable_stories():
    user = get_user_model().objects.create_user(username="no-stories@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.EVIDENCE_APPROVED)

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_stories_ready(user=user, sprint=sprint, has_usable_stories=False)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.EVIDENCE_APPROVED


@pytest.mark.django_db
def test_mark_stories_ready_rejects_skip_from_evidence_review():
    user = get_user_model().objects.create_user(username="skip-stories@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.EVIDENCE_REVIEW)

    with pytest.raises(InvalidSprintTransition):
        SprintWorkflowService.mark_stories_ready(user=user, sprint=sprint, has_usable_stories=True)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.EVIDENCE_REVIEW
