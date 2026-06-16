from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from ai.schemas.company_context import CompanyContext
from ai.services import AICompanyContextExtractionError, AIJDAnalysisError, EvidraAIService
from apps.opportunities.company_context import CompanyContextFetcher, CompanyContextFetchError
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
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
        update_fields = ["jd_analysis", "updated_at"]
        if (
            opportunity.company_context
            and opportunity.company_context_status == CompanyContextStatus.CONFIRMED
        ):
            opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
            update_fields.append("company_context_status")
        opportunity.save(update_fields=update_fields)
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
        return opportunity

    @staticmethod
    def extract_company_context_from_url(
        *,
        user,
        sprint: InterviewSprint,
        opportunity_id,
        company_url: str,
        fetcher: CompanyContextFetcher | None = None,
        ai_service: EvidraAIService | None = None,
    ) -> Opportunity:
        opportunity = OpportunityService._get_editable_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity_id
        )
        try:
            fetch_result = (fetcher or CompanyContextFetcher()).fetch(company_url)
            context = (ai_service or EvidraAIService()).extract_company_context(
                source_text=fetch_result.visible_text,
                source_type="url",
                source_url=fetch_result.final_url,
            )
        except (CompanyContextFetchError, AICompanyContextExtractionError):
            opportunity.company_context_status = CompanyContextStatus.FAILED
            opportunity.save(update_fields=["company_context_status", "updated_at"])
            raise
        opportunity.company_url = fetch_result.final_url
        opportunity.company_context = context.model_dump(mode="json")
        opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
        opportunity.save(
            update_fields=[
                "company_url",
                "company_context",
                "company_context_status",
                "updated_at",
            ]
        )
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
        return opportunity

    @staticmethod
    def extract_company_context_from_paste(
        *,
        user,
        sprint: InterviewSprint,
        opportunity_id,
        pasted_company_context: str,
        ai_service: EvidraAIService | None = None,
    ) -> Opportunity:
        opportunity = OpportunityService._get_editable_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity_id
        )
        try:
            context = (ai_service or EvidraAIService()).extract_company_context(
                source_text=pasted_company_context,
                source_type="paste",
                source_url=None,
            )
        except AICompanyContextExtractionError:
            opportunity.company_context_status = CompanyContextStatus.FAILED
            opportunity.save(update_fields=["company_context_status", "updated_at"])
            raise
        opportunity.company_url = ""
        opportunity.company_context = context.model_dump(mode="json")
        opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
        opportunity.save(
            update_fields=[
                "company_url",
                "company_context",
                "company_context_status",
                "updated_at",
            ]
        )
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
        return opportunity



    @staticmethod
    def update_company_context_review(
        *, user, sprint: InterviewSprint, opportunity_id, company_context_payload: dict[str, Any]
    ) -> Opportunity:
        opportunity = OpportunityService._get_editable_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity_id
        )
        if not opportunity.company_context:
            raise OpportunityError("Extract or paste company context before reviewing it.")
        reviewed_payload = {
            **company_context_payload,
            "source_type": opportunity.company_context.get("source_type") or "paste",
            "source_url": opportunity.company_context.get("source_url"),
            "source_references": [],
        }
        context = CompanyContext.model_validate(reviewed_payload)
        opportunity.company_context = context.model_dump(mode="json")
        opportunity.company_context_status = CompanyContextStatus.PENDING_REVIEW
        opportunity.save(update_fields=["company_context", "company_context_status", "updated_at"])
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
        return opportunity

    @staticmethod
    def confirm_company_context(*, user, sprint: InterviewSprint, opportunity_id) -> Opportunity:
        opportunity = OpportunityService._get_editable_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity_id
        )
        if not opportunity.company_context:
            raise OpportunityError("Review extracted company context before confirming it.")
        opportunity.company_context_status = CompanyContextStatus.CONFIRMED
        opportunity.save(update_fields=["company_context_status", "updated_at"])
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
        return opportunity

    @staticmethod
    def skip_company_context(*, user, sprint: InterviewSprint, opportunity_id) -> Opportunity:
        opportunity = OpportunityService._get_editable_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity_id
        )
        if opportunity.company_context_status == CompanyContextStatus.CONFIRMED:
            raise OpportunityError(
                "Confirmed company context cannot be skipped without editing it."
            )
        opportunity.company_context_status = CompanyContextStatus.SKIPPED
        opportunity.save(update_fields=["company_context_status", "updated_at"])
        OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
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
            OpportunityService._mark_prepkit_stale(user=user, sprint=sprint)
            return opportunity

    @staticmethod
    def _mark_prepkit_stale(*, user, sprint: InterviewSprint) -> None:
        from apps.prepkits.services import PrepKitService

        PrepKitService.mark_stale_for_sprint(user=user, sprint=sprint)

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
        if opportunity.company_context_status not in {
            CompanyContextStatus.CONFIRMED,
            CompanyContextStatus.SKIPPED,
        }:
            raise OpportunityError(
                "Confirm company context or choose continue without company context "
                "before confirming."
            )

    @staticmethod
    def _get_editable_opportunity(*, user, sprint: InterviewSprint, opportunity_id) -> Opportunity:
        OpportunityService._require_opportunity_stage_ready(user=user, sprint=sprint)
        opportunity = (
            Opportunity.objects.select_related("sprint")
            .filter(pk=opportunity_id, sprint__user=user, sprint=sprint)
            .first()
        )
        if opportunity is None:
            raise Http404("Opportunity not found.")
        if not opportunity.jd_analysis:
            raise OpportunityError("Analyze the job description before company context.")
        return opportunity
