from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
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
            locked_sprint = InterviewSprint.objects.select_for_update().get(
                pk=sprint.pk,
                user=user,
            )
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

    @staticmethod
    def mark_resume_ready(*, user, sprint: InterviewSprint, document) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id or document.user_id != user.id:
            raise SprintOwnershipError("Sprint or resume is not owned by this user.")
        has_confirmed_resume = (
            document.is_active
            and document.parsing_status == "CONFIRMED"
            and document.cleaned_text.strip()
        )
        if not has_confirmed_resume:
            raise SprintTransitionConditionMissing(
                "A confirmed active resume is required before moving to RESUME_READY."
            )

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(
                pk=sprint.pk,
                user=user,
            )
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.RESUME_READY:
                if locked_sprint.active_resume_id != document.pk:
                    locked_sprint.active_resume = document
                    locked_sprint.save(update_fields=["active_resume", "updated_at"])
                return locked_sprint
            if current_state != SprintState.DRAFT:
                raise InvalidSprintTransition(
                    f"Cannot mark resume ready while Sprint is in {current_state}."
                )

            locked_sprint.active_resume = document
            locked_sprint.state = SprintState.RESUME_READY
            locked_sprint.save(update_fields=["active_resume", "state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_profile_confirmed(*, user, sprint: InterviewSprint, profile) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id or profile.user_id != user.id:
            raise SprintOwnershipError("Sprint or profile is not owned by this user.")
        has_confirmed_profile = (
            profile.confirmation_status == "CONFIRMED"
            and sprint.active_resume_id == profile.active_resume_id
        )
        if not has_confirmed_profile:
            raise SprintTransitionConditionMissing(
                "A confirmed profile for the active resume is required."
            )

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(
                pk=sprint.pk,
                user=user,
            )
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PROFILE_CONFIRMED:
                if locked_sprint.active_profile_id != profile.pk:
                    raise InvalidSprintTransition(
                        "Cannot replace a confirmed Sprint profile in this stage."
                    )
                return locked_sprint
            if current_state != SprintState.RESUME_READY:
                raise InvalidSprintTransition(
                    f"Cannot mark profile confirmed while Sprint is in {current_state}."
                )
            if locked_sprint.active_resume_id != profile.active_resume_id:
                raise SprintTransitionConditionMissing(
                    "Profile must belong to the Sprint's active resume."
                )

            locked_sprint.active_profile = profile
            locked_sprint.state = SprintState.PROFILE_CONFIRMED
            locked_sprint.save(update_fields=["active_profile", "state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_opportunity_confirmed(
        *, user, sprint: InterviewSprint, opportunity
    ) -> InterviewSprint:
        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or opportunity.sprint_id != sprint.id
            or opportunity.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or opportunity is not owned by this user.")
        has_confirmed_opportunity = (
            opportunity.confirmation_status == "CONFIRMED"
            and bool(opportunity.role_family)
            and bool(opportunity.job_description.strip())
            and bool(opportunity.jd_analysis)
        )
        if not has_confirmed_opportunity:
            raise SprintTransitionConditionMissing("A confirmed analyzed opportunity is required.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(
                pk=sprint.pk,
                user=user,
            )
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.OPPORTUNITY_CONFIRMED:
                return locked_sprint
            if current_state != SprintState.PROFILE_CONFIRMED:
                raise InvalidSprintTransition(
                    f"Cannot mark opportunity confirmed while Sprint is in {current_state}."
                )
            if locked_sprint.active_profile_id is None:
                raise SprintTransitionConditionMissing(
                    "A confirmed active profile is required before opportunity confirmation."
                )

            locked_sprint.state = SprintState.OPPORTUNITY_CONFIRMED
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_evidence_review_started(
        *, user, sprint: InterviewSprint, has_reviewable_evidence: bool
    ) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if not has_reviewable_evidence:
            raise SprintTransitionConditionMissing(
                "Evidence candidates or manual highlights are required for review."
            )

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.EVIDENCE_REVIEW:
                return locked_sprint
            if current_state != SprintState.OPPORTUNITY_CONFIRMED:
                raise InvalidSprintTransition(
                    f"Cannot start evidence review while Sprint is in {current_state}."
                )
            if locked_sprint.active_profile_id is None or locked_sprint.active_resume_id is None:
                raise SprintTransitionConditionMissing(
                    "A confirmed active resume and profile are required before evidence review."
                )
            locked_sprint.state = SprintState.EVIDENCE_REVIEW
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_evidence_approved(
        *, user, sprint: InterviewSprint, threshold_met: bool
    ) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if not threshold_met:
            raise SprintTransitionConditionMissing("Evidence approval threshold has not been met.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.EVIDENCE_APPROVED:
                return locked_sprint
            if current_state != SprintState.EVIDENCE_REVIEW:
                raise InvalidSprintTransition(
                    f"Cannot approve evidence while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.EVIDENCE_APPROVED
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_stories_ready(
        *, user, sprint: InterviewSprint, has_usable_stories: bool
    ) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if not has_usable_stories:
            raise SprintTransitionConditionMissing("Reusable stories are required.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.STORIES_READY:
                return locked_sprint
            if current_state != SprintState.EVIDENCE_APPROVED:
                raise InvalidSprintTransition(
                    f"Cannot mark stories ready while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.STORIES_READY
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_matching_ready(
        *, user, sprint: InterviewSprint, has_matches_or_gaps: bool
    ) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if not has_matches_or_gaps:
            raise SprintTransitionConditionMissing("Story matches or explicit gaps are required.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.MATCHING_READY:
                return locked_sprint
            if current_state != SprintState.STORIES_READY:
                raise InvalidSprintTransition(
                    f"Cannot mark matching ready while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.MATCHING_READY
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_matching_stale(*, user, sprint: InterviewSprint) -> InterviewSprint:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.MATCHING_READY:
                locked_sprint.state = SprintState.STORIES_READY
                locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_preview_ready(*, user, sprint: InterviewSprint, preview) -> InterviewSprint:
        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or preview.sprint_id != sprint.id
            or preview.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or preview is not owned by this user.")
        if preview.status != "READY":
            raise SprintTransitionConditionMissing("A ready preview is required.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PREVIEW_READY:
                return locked_sprint
            if current_state != SprintState.MATCHING_READY:
                raise InvalidSprintTransition(
                    f"Cannot mark preview ready while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.PREVIEW_READY
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_payment_pending(*, user, sprint: InterviewSprint, payment) -> InterviewSprint:
        from apps.payments.models import Payment, PaymentStatus

        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or payment.user_id != user.id
            or payment.sprint_id != sprint.id
            or payment.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or payment is not owned by this user.")
        if payment.provider != Payment.PROVIDER_RAZORPAY:
            raise SprintTransitionConditionMissing("A Razorpay payment is required.")
        if not payment.provider_order_id:
            raise SprintTransitionConditionMissing(
                "A Razorpay order is required before payment pending."
            )
        if payment.status not in {PaymentStatus.ORDER_CREATED, PaymentStatus.PAYMENT_PENDING}:
            raise SprintTransitionConditionMissing("An active payment order is required.")
        SprintWorkflowService._validate_expected_payment_terms(payment=payment)

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PAYMENT_PENDING:
                return locked_sprint
            if current_state != SprintState.PREVIEW_READY:
                raise InvalidSprintTransition(
                    f"Cannot mark payment pending while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.PAYMENT_PENDING
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_paid(*, user, sprint: InterviewSprint, payment) -> InterviewSprint:
        from apps.payments.models import Payment, PaymentStatus

        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or payment.user_id != user.id
            or payment.sprint_id != sprint.id
            or payment.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or payment is not owned by this user.")
        if payment.provider != Payment.PROVIDER_RAZORPAY:
            raise SprintTransitionConditionMissing("A Razorpay payment is required.")
        if (
            payment.status != PaymentStatus.PAID
            or not payment.provider_order_id
            or not payment.provider_payment_id
            or payment.paid_at is None
        ):
            raise SprintTransitionConditionMissing("A verified paid payment is required.")
        SprintWorkflowService._validate_expected_payment_terms(payment=payment)

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PAID:
                return locked_sprint
            if current_state != SprintState.PAYMENT_PENDING:
                raise InvalidSprintTransition(
                    f"Cannot mark paid while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.PAID
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_prepkit_ready(*, user, sprint: InterviewSprint, prepkit) -> InterviewSprint:
        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or prepkit.sprint_id != sprint.id
            or prepkit.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or Prep Kit is not owned by this user.")
        if prepkit.status != "READY" or prepkit.generated_at is None:
            raise SprintTransitionConditionMissing("A ready Prep Kit is required.")
        from apps.prepkits.services import PrepKitService

        current_revision = PrepKitService.current_input_revision(user=user, sprint=sprint)
        if prepkit.input_revision != current_revision:
            raise SprintTransitionConditionMissing("A current Prep Kit is required.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PREPKIT_READY:
                return locked_sprint
            if current_state != SprintState.PAID:
                raise InvalidSprintTransition(
                    f"Cannot mark Prep Kit ready while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.PREPKIT_READY
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def mark_practice_active(*, user, sprint: InterviewSprint, attempt) -> InterviewSprint:
        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or attempt.sprint_id != sprint.id
            or attempt.sprint.user_id != user.id
        ):
            raise SprintOwnershipError("Sprint or practice attempt is not owned by this user.")

        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            from apps.practice.models import PracticeAttempt

            if (
                not attempt.pk
                or not PracticeAttempt.objects.filter(
                    pk=attempt.pk, sprint=locked_sprint, sprint__user=user
                ).exists()
            ):
                raise SprintTransitionConditionMissing(
                    "A persisted practice attempt is required before practice can become active."
                )
            current_state = SprintState(locked_sprint.state)
            if current_state == SprintState.PRACTICE_ACTIVE:
                return locked_sprint
            if current_state != SprintState.PREPKIT_READY:
                raise InvalidSprintTransition(
                    f"Cannot mark practice active while Sprint is in {current_state}."
                )
            locked_sprint.state = SprintState.PRACTICE_ACTIVE
            locked_sprint.save(update_fields=["state", "updated_at"])
            return locked_sprint

    @staticmethod
    def _validate_expected_payment_terms(*, payment) -> None:
        expected_amount = int(getattr(settings, "INTERVIEW_SPRINT_PRICE_AMOUNT", 0) or 0)
        expected_currency = (getattr(settings, "INTERVIEW_SPRINT_PRICE_CURRENCY", "") or "").upper()
        if expected_amount <= 0 or len(expected_currency) != 3:
            raise SprintTransitionConditionMissing(
                "Expected payment amount and currency are required."
            )
        if payment.amount != expected_amount or payment.currency.upper() != expected_currency:
            raise SprintTransitionConditionMissing(
                "Payment amount and currency must match the Interview Sprint price."
            )
