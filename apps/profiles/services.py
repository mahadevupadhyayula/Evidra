from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from ai.schemas.profile import ExtractedProfile
from ai.services import AIProfileExtractionError, EvidraAIService
from apps.documents.models import DocumentParsingStatus, DocumentType
from apps.profiles.models import CareerProfile, CareerProfileStatus, ProfileExtractionStatus
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)

PROFILE_EDITABLE_FIELDS = [
    "full_name",
    "current_role",
    "current_company",
    "years_experience",
    "industries",
    "functional_areas",
    "skills",
    "tools",
    "education_summary",
    "career_summary",
    "positioning_summary",
]


class CareerProfileError(ValueError):
    """Raised when a profile action fails deterministic validation."""


@dataclass(frozen=True)
class CareerProfileService:
    @staticmethod
    def get_owned_profile(user, profile_id) -> CareerProfile:
        if not user.is_authenticated:
            raise Http404("Profile not found.")
        try:
            return CareerProfile.objects.select_related("active_resume").get(
                pk=profile_id,
                user=user,
            )
        except CareerProfile.DoesNotExist as exc:
            raise Http404("Profile not found.") from exc

    @staticmethod
    def get_current_profile(user, sprint: InterviewSprint) -> CareerProfile | None:
        CareerProfileService._require_owned_sprint(user=user, sprint=sprint)
        if sprint.active_profile_id:
            return CareerProfile.objects.filter(pk=sprint.active_profile_id, user=user).first()
        if not sprint.active_resume_id:
            return None
        return (
            CareerProfile.objects.filter(user=user, active_resume_id=sprint.active_resume_id)
            .exclude(confirmation_status=CareerProfileStatus.STALE)
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def ensure_draft_profile(
        *,
        user,
        sprint: InterviewSprint,
        ai_service: EvidraAIService | None = None,
    ) -> CareerProfile:
        CareerProfileService._require_profile_stage_ready(user=user, sprint=sprint)
        profile = CareerProfileService.get_or_create_draft_profile(user=user, sprint=sprint)
        if profile.extraction_status == ProfileExtractionStatus.SUCCEEDED:
            return profile

        active_resume = sprint.active_resume
        if active_resume is None:
            raise CareerProfileError("Confirm your resume before creating your profile.")

        try:
            extracted_profile = (ai_service or EvidraAIService()).extract_profile(
                active_resume.cleaned_text,
            )
        except AIProfileExtractionError as exc:
            profile.extraction_status = ProfileExtractionStatus.FAILED
            profile.extraction_error = str(exc)
            profile.ai_attempt_count = 2
            profile.save(
                update_fields=[
                    "extraction_status",
                    "extraction_error",
                    "ai_attempt_count",
                    "updated_at",
                ]
            )
            raise
        return CareerProfileService._update_from_extracted_profile(
            profile=profile,
            extracted_profile=extracted_profile,
        )

    @staticmethod
    def get_or_create_draft_profile(*, user, sprint: InterviewSprint) -> CareerProfile:
        CareerProfileService._require_profile_stage_ready(user=user, sprint=sprint)
        active_resume = sprint.active_resume
        if active_resume is None:
            raise CareerProfileError("Confirm your resume before creating your profile.")
        try:
            with transaction.atomic():
                existing = (
                    CareerProfile.objects.select_for_update()
                    .filter(user=user, active_resume=active_resume)
                    .exclude(confirmation_status=CareerProfileStatus.STALE)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if existing is not None:
                    return existing
                return CareerProfile.objects.create(user=user, active_resume=active_resume)
        except IntegrityError:
            return (
                CareerProfile.objects.filter(user=user, active_resume=active_resume)
                .exclude(confirmation_status=CareerProfileStatus.STALE)
                .order_by("-created_at", "-id")
                .get()
            )

    @staticmethod
    def update_profile(*, user, profile_id, cleaned_data: dict[str, Any]) -> CareerProfile:
        profile = CareerProfileService.get_owned_profile(user, profile_id)
        if profile.confirmation_status != CareerProfileStatus.DRAFT:
            raise CareerProfileError("Confirmed profiles cannot be edited in this stage.")
        for field_name in PROFILE_EDITABLE_FIELDS:
            setattr(profile, field_name, cleaned_data.get(field_name))
        profile.save(update_fields=[*PROFILE_EDITABLE_FIELDS, "updated_at"])
        return profile

    @staticmethod
    def confirm_profile(
        *,
        user,
        sprint: InterviewSprint,
        profile_id,
        cleaned_data: dict[str, Any],
    ) -> CareerProfile:
        CareerProfileService._require_owned_sprint(user=user, sprint=sprint)
        with transaction.atomic():
            profile = (
                CareerProfile.objects.select_for_update()
                .select_related("active_resume")
                .filter(
                    pk=profile_id,
                    user=user,
                )
                .first()
            )
            if profile is None:
                raise Http404("Profile not found.")
            if profile.confirmation_status == CareerProfileStatus.CONFIRMED:
                SprintWorkflowService.mark_profile_confirmed(
                    user=user,
                    sprint=sprint,
                    profile=profile,
                )
                return profile
            if profile.confirmation_status != CareerProfileStatus.DRAFT:
                raise CareerProfileError("Only draft profiles can be confirmed.")
            for field_name in PROFILE_EDITABLE_FIELDS:
                setattr(profile, field_name, cleaned_data.get(field_name))
            profile.confirmation_status = CareerProfileStatus.CONFIRMED
            if profile.confirmed_at is None:
                profile.confirmed_at = timezone.now()
            profile.save(
                update_fields=[
                    *PROFILE_EDITABLE_FIELDS,
                    "confirmation_status",
                    "confirmed_at",
                    "updated_at",
                ]
            )
            SprintWorkflowService.mark_profile_confirmed(user=user, sprint=sprint, profile=profile)
            return profile

    @staticmethod
    def _update_from_extracted_profile(
        *,
        profile: CareerProfile,
        extracted_profile: ExtractedProfile,
    ) -> CareerProfile:
        for field_name, value in {
            "full_name": extracted_profile.full_name,
            "current_role": extracted_profile.current_role,
            "current_company": extracted_profile.current_company,
            "years_experience": extracted_profile.years_experience,
            "industries": extracted_profile.industries,
            "functional_areas": extracted_profile.functional_areas,
            "skills": extracted_profile.skills,
            "tools": extracted_profile.tools,
            "education_summary": extracted_profile.education_summary,
            "career_summary": extracted_profile.career_summary,
            "positioning_summary": extracted_profile.positioning_summary,
        }.items():
            setattr(profile, field_name, value)
        profile.extraction_status = ProfileExtractionStatus.SUCCEEDED
        profile.extraction_error = ""
        profile.ai_attempt_count = 1
        profile.save(
            update_fields=[
                *PROFILE_EDITABLE_FIELDS,
                "extraction_status",
                "extraction_error",
                "ai_attempt_count",
                "updated_at",
            ]
        )
        return profile

    @staticmethod
    def _require_owned_sprint(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

    @staticmethod
    def _require_profile_stage_ready(*, user, sprint: InterviewSprint) -> None:
        CareerProfileService._require_owned_sprint(user=user, sprint=sprint)
        if sprint.state != SprintState.RESUME_READY:
            raise InvalidSprintTransition("Profile extraction requires a resume-ready Sprint.")
        active_resume = sprint.active_resume
        if active_resume is None:
            raise SprintTransitionConditionMissing("A confirmed active resume is required.")
        if (
            active_resume.user_id != user.id
            or active_resume.document_type != DocumentType.RESUME
            or not active_resume.is_active
            or active_resume.parsing_status != DocumentParsingStatus.CONFIRMED
            or not active_resume.cleaned_text.strip()
        ):
            raise SprintTransitionConditionMissing("A confirmed active resume is required.")
