from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from ai.services import AIJDAnalysisError, EvidraAIService
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.opportunities.role_packs import get_role_pack, role_pack_as_prompt_context
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


class OpportunityError(ValueError):
    """Raised when an opportunity cannot be saved or confirmed."""


OPPORTUNITY_EDITABLE_FIELDS = [
    "role_title",
    "role_family",
    "target_seniority",
    "company_name",
    "job_description",
    "interview_stage",
    "interview_date",
    "concerns",
    "improvement_goals",
]


@dataclass(frozen=True)
class OpportunityService:
    @staticmethod
    def get_owned_opportunity(user, opportunity_id) -> Opportunity:
        if not user.is_authenticated:
            raise Http404("Opportunity not found.")
        try:
            return Opportunity.objects.select_related("sprint").get(
                pk=opportunity_id,
                sprint__user=user,
            )
        except Opportunity.DoesNotExist as exc:
            raise Http404("Opportunity not found.") from exc

    @staticmethod
    def get_current_opportunity(*, user, sprint: InterviewSprint) -> Opportunity | None:
        OpportunityService._require_owned_sprint(user=user, sprint=sprint)
        return (
            Opportunity.objects.select_related("sprint")
            .filter(sprint=sprint)
            .exclude(confirmation_status=OpportunityStatus.STALE)
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def get_or_create_draft_opportunity(*, user, sprint: InterviewSprint) -> Opportunity:
        OpportunityService._require_opportunity_stage_ready(user=user, sprint=sprint)
        try:
            with transaction.atomic():
                existing = (
                    Opportunity.objects.select_for_update()
                    .filter(sprint=sprint)
                    .exclude(confirmation_status=OpportunityStatus.STALE)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if existing is not None:
                    return existing
                return Opportunity.objects.create(
                    sprint=sprint,
                    role_title="",
                    role_family="PRODUCT_MANAGEMENT",
                    target_seniority="",
                    company_name="",
                    job_description="",
                )
        except IntegrityError:
            return (
                Opportunity.objects.filter(sprint=sprint)
                .exclude(confirmation_status=OpportunityStatus.STALE)
                .order_by("-created_at", "-id")
                .get()
            )

    @staticmethod
    def analyze_and_save_opportunity(
        *,
        user,
        sprint: InterviewSprint,
        cleaned_data: dict[str, Any],
        ai_service: EvidraAIService | None = None,
    ) -> Opportunity:
        OpportunityService._require_opportunity_stage_ready(user=user, sprint=sprint)
        role_pack = get_role_pack(cleaned_data["role_family"])
        opportunity = OpportunityService.get_or_create_draft_opportunity(user=user, sprint=sprint)
        for field_name in OPPORTUNITY_EDITABLE_FIELDS:
            if field_name == "interview_date":
                setattr(opportunity, field_name, cleaned_data.get(field_name))
            else:
                setattr(opportunity, field_name, cleaned_data.get(field_name) or "")
        opportunity.confirmation_status = OpportunityStatus.DRAFT
        opportunity.jd_analysis = None
        opportunity.save(
            update_fields=[
                *OPPORTUNITY_EDITABLE_FIELDS,
                "confirmation_status",
                "jd_analysis",
                "updated_at",
            ]
        )

        try:
            analysis = (ai_service or EvidraAIService()).analyze_jd(
                job_description=opportunity.job_description,
                role_title=opportunity.role_title,
                role_family=opportunity.role_family,
                target_seniority=opportunity.target_seniority,
                role_pack=role_pack_as_prompt_context(role_pack),
            )
        except AIJDAnalysisError:
            raise
        opportunity.jd_analysis = analysis.model_dump(mode="json")
        opportunity.save(update_fields=["jd_analysis", "updated_at"])
        return opportunity

    @staticmethod
    def confirm_opportunity(*, user, sprint: InterviewSprint, opportunity_id) -> Opportunity:
        OpportunityService._require_owned_sprint(user=user, sprint=sprint)
        with transaction.atomic():
            opportunity = (
                Opportunity.objects.select_for_update()
                .select_related("sprint")
                .filter(pk=opportunity_id, sprint__user=user, sprint=sprint)
                .first()
            )
            if opportunity is None:
                raise Http404("Opportunity not found.")
            if opportunity.confirmation_status == OpportunityStatus.CONFIRMED:
                SprintWorkflowService.mark_opportunity_confirmed(
                    user=user,
                    sprint=sprint,
                    opportunity=opportunity,
                )
                return opportunity
            OpportunityService._validate_confirmable_opportunity(opportunity)
            opportunity.confirmation_status = OpportunityStatus.CONFIRMED
            if opportunity.confirmed_at is None:
                opportunity.confirmed_at = timezone.now()
            opportunity.save(update_fields=["confirmation_status", "confirmed_at", "updated_at"])
            SprintWorkflowService.mark_opportunity_confirmed(
                user=user,
                sprint=sprint,
                opportunity=opportunity,
            )
            return opportunity

    @staticmethod
    def _require_owned_sprint(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

    @staticmethod
    def _require_opportunity_stage_ready(*, user, sprint: InterviewSprint) -> None:
        OpportunityService._require_owned_sprint(user=user, sprint=sprint)
        if sprint.state != SprintState.PROFILE_CONFIRMED:
            raise InvalidSprintTransition(
                "Opportunity analysis requires a profile-confirmed Sprint."
            )
        if sprint.active_profile_id is None:
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")
        if (
            sprint.active_profile.user_id != user.id
            or sprint.active_profile.confirmation_status != "CONFIRMED"
        ):
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")

    @staticmethod
    def _validate_confirmable_opportunity(opportunity: Opportunity) -> None:
        missing_fields = [
            field_name
            for field_name in [
                "role_title",
                "role_family",
                "target_seniority",
                "company_name",
                "job_description",
            ]
            if not getattr(opportunity, field_name)
        ]
        if missing_fields or not opportunity.jd_analysis:
            raise OpportunityError("Analyze and review the opportunity before confirming it.")
