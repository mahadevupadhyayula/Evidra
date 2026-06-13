from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.http import Http404

from apps.sprints.models import InterviewSprint, SprintState


class InvalidSprintTransition(ValueError):
    """Raised when a requested Sprint state transition is not allowed."""


class SprintOwnershipError(PermissionError):
    """Raised when a Sprint is not owned by the expected user."""


class SprintTransitionConditionMissing(PermissionError):
    """Raised when a stage-specific service has not validated transition conditions."""


ALLOWED_TRANSITIONS: dict[SprintState, set[SprintState]] = {
    SprintState.DRAFT: {SprintState.RESUME_READY},
    SprintState.RESUME_READY: {SprintState.PROFILE_CONFIRMED},
    SprintState.PROFILE_CONFIRMED: {SprintState.OPPORTUNITY_CONFIRMED},
    SprintState.OPPORTUNITY_CONFIRMED: {SprintState.EVIDENCE_REVIEW},
    SprintState.EVIDENCE_REVIEW: {SprintState.EVIDENCE_APPROVED},
    SprintState.EVIDENCE_APPROVED: {SprintState.STORIES_READY},
    SprintState.STORIES_READY: {SprintState.MATCHING_READY},
    SprintState.MATCHING_READY: {SprintState.PREVIEW_READY},
    SprintState.PREVIEW_READY: {SprintState.PAYMENT_PENDING},
    SprintState.PAYMENT_PENDING: {SprintState.PAID},
    SprintState.PAID: {SprintState.PREPKIT_READY},
    SprintState.PREPKIT_READY: {SprintState.PRACTICE_ACTIVE},
    SprintState.PRACTICE_ACTIVE: {SprintState.PLAN_READY},
    SprintState.PLAN_READY: {SprintState.COMPLETED},
    SprintState.COMPLETED: set(),
}

TERMINAL_STATES = {SprintState.COMPLETED}


@dataclass(frozen=True)
class SprintWorkflowService:
    """Owns deterministic Interview Sprint workflow rules and ownership checks."""

    @staticmethod
    def get_or_create_current_sprint(user) -> InterviewSprint:
        if not user.is_authenticated:
            raise SprintOwnershipError("A signed-in user is required to own a Sprint.")

        try:
            with transaction.atomic():
                sprint = (
                    InterviewSprint.objects.select_for_update()
                    .filter(user=user)
                    .exclude(state__in=TERMINAL_STATES)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if sprint is not None:
                    return sprint
                return InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)
        except IntegrityError:
            return (
                InterviewSprint.objects.filter(user=user)
                .exclude(state__in=TERMINAL_STATES)
                .order_by("-created_at", "-id")
                .get()
            )

    @staticmethod
    def get_owned_sprint(user, sprint_id) -> InterviewSprint:
        if not user.is_authenticated:
            raise Http404("Sprint not found.")
        try:
            return InterviewSprint.objects.get(pk=sprint_id, user=user)
        except InterviewSprint.DoesNotExist as exc:
            raise Http404("Sprint not found.") from exc

    @staticmethod
    def transition(
        *, user, sprint: InterviewSprint, to_state: SprintState | str
    ) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

        target_state = SprintState(to_state)
        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            allowed_targets = ALLOWED_TRANSITIONS[current_state]
            if target_state not in allowed_targets:
                raise InvalidSprintTransition(
                    f"Cannot transition Sprint from {current_state} to {target_state}."
                )

            raise SprintTransitionConditionMissing(
                f"Transition from {current_state} to {target_state} requires "
                "stage-specific condition validation."
            )
