from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.http import Http404

from ai.services import EvidraAIService
from apps.documents.models import DocumentParsingStatus
from apps.evidence.models import (
    CareerHighlight,
    CareerHighlightStatus,
    EvidenceCard,
    EvidenceStatus,
)
from apps.opportunities.models import OpportunityStatus
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


class EvidenceError(ValueError):
    """Raised when evidence cannot be reviewed or approved safely."""


@dataclass(frozen=True)
class EvidenceThresholdResult:
    approved_count: int
    clear_result_count: int
    all_have_provenance: bool
    metrics_valid: bool

    @property
    def is_met(self) -> bool:
        return (
            self.approved_count >= 3
            and self.clear_result_count >= 2
            and self.all_have_provenance
            and self.metrics_valid
        )


CARD_EDITABLE_FIELDS = [
    "title",
    "problem",
    "role",
    "action",
    "result",
    "metric",
    "skills",
    "competencies",
    "ownership_signal",
    "constraints",
    "tradeoffs",
    "missing_details",
    "source_excerpt",
    "source_location",
    "confidentiality",
]


@dataclass(frozen=True)
class EvidenceService:
    @staticmethod
    def list_highlights(*, user, sprint: InterviewSprint):
        EvidenceService._require_evidence_stage_readable(user=user, sprint=sprint)
        return CareerHighlight.objects.filter(
            user=user,
            profile=sprint.active_profile,
        ).exclude(status=CareerHighlightStatus.STALE)

    @staticmethod
    def list_cards(*, user, sprint: InterviewSprint):
        EvidenceService._require_evidence_stage_readable(user=user, sprint=sprint)
        return EvidenceCard.objects.select_related(
            "source_document", "source_highlight", "duplicate_of"
        ).filter(user=user, profile=sprint.active_profile)

    @staticmethod
    def create_highlight(
        *, user, sprint: InterviewSprint, cleaned_data: dict[str, Any]
    ) -> CareerHighlight:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        with transaction.atomic():
            highlight = CareerHighlight.objects.create(
                user=user,
                profile=sprint.active_profile,
                title=cleaned_data["title"],
                description=cleaned_data["description"],
                metric=cleaned_data.get("metric"),
                skills=cleaned_data.get("skills_text", []),
                source_note=cleaned_data.get("source_note", ""),
                status=CareerHighlightStatus.ACTIVE,
            )
            SprintWorkflowService.mark_evidence_review_started(
                user=user,
                sprint=sprint,
                has_reviewable_evidence=True,
            )
            return highlight

    @staticmethod
    def update_highlight(
        *, user, sprint: InterviewSprint, highlight_id, cleaned_data: dict[str, Any]
    ) -> CareerHighlight:
        EvidenceService._require_evidence_review_mutable(user=user, sprint=sprint)
        highlight = EvidenceService.get_owned_highlight(
            user=user, sprint=sprint, highlight_id=highlight_id
        )
        with transaction.atomic():
            for field, value in {
                "title": cleaned_data["title"],
                "description": cleaned_data["description"],
                "metric": cleaned_data.get("metric"),
                "skills": cleaned_data.get("skills_text", []),
                "source_note": cleaned_data.get("source_note", ""),
            }.items():
                setattr(highlight, field, value)
            highlight.save(
                update_fields=[
                    "title",
                    "description",
                    "metric",
                    "skills",
                    "source_note",
                    "updated_at",
                ]
            )
            EvidenceCard.objects.filter(
                user=user,
                profile=sprint.active_profile,
                source_highlight=highlight,
            ).update(status=EvidenceStatus.STALE)
        return highlight

    @staticmethod
    def archive_highlight(*, user, sprint: InterviewSprint, highlight_id) -> CareerHighlight:
        EvidenceService._require_evidence_review_mutable(user=user, sprint=sprint)
        highlight = EvidenceService.get_owned_highlight(
            user=user, sprint=sprint, highlight_id=highlight_id
        )
        with transaction.atomic():
            highlight.status = CareerHighlightStatus.STALE
            highlight.save(update_fields=["status", "updated_at"])
            EvidenceCard.objects.filter(
                user=user,
                profile=sprint.active_profile,
                source_highlight=highlight,
            ).update(status=EvidenceStatus.STALE)
        return highlight

    @staticmethod
    def get_owned_highlight(*, user, sprint: InterviewSprint, highlight_id) -> CareerHighlight:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        try:
            return CareerHighlight.objects.get(
                pk=highlight_id,
                user=user,
                profile=sprint.active_profile,
            )
        except CareerHighlight.DoesNotExist as exc:
            raise Http404("Highlight not found.") from exc

    @staticmethod
    def get_owned_card(*, user, sprint: InterviewSprint, card_id) -> EvidenceCard:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        try:
            return EvidenceCard.objects.select_related(
                "source_document", "source_highlight", "duplicate_of"
            ).get(pk=card_id, user=user, profile=sprint.active_profile)
        except EvidenceCard.DoesNotExist as exc:
            raise Http404("Evidence card not found.") from exc

    @staticmethod
    def extract_evidence(
        *, user, sprint: InterviewSprint, ai_service: EvidraAIService | None = None
    ) -> int:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        active_resume = sprint.active_resume
        active_profile = sprint.active_profile
        if active_resume is None or active_profile is None:
            raise EvidenceError("Confirm your resume and profile before extracting evidence.")
        highlights = list(
            CareerHighlight.objects.filter(
                user=user,
                profile=active_profile,
                status=CareerHighlightStatus.ACTIVE,
            ).order_by("created_at", "id")
        )
        highlight_payload = [
            {
                "id": highlight.id,
                "title": highlight.title,
                "description": highlight.description,
                "metric": highlight.metric,
                "skills": highlight.skills,
                "source_note": highlight.source_note,
            }
            for highlight in highlights
        ]
        opportunity = EvidenceService._get_confirmed_opportunity(user=user, sprint=sprint)
        extracted = (ai_service or EvidraAIService()).extract_evidence(
            resume_text=active_resume.cleaned_text,
            highlights=highlight_payload,
            profile_context={
                "current_role": active_profile.current_role,
                "current_company": active_profile.current_company,
                "skills": active_profile.skills,
                "positioning_summary": active_profile.positioning_summary,
            },
            opportunity_context={
                "role_title": opportunity.role_title,
                "role_family": opportunity.role_family,
                "target_seniority": opportunity.target_seniority,
                "company_name": opportunity.company_name,
                "jd_analysis": opportunity.jd_analysis,
            },
        )
        created_count = 0
        with transaction.atomic():
            for card in extracted.cards:
                source_highlight = None
                source_document = active_resume
                if card.source_type == "highlight":
                    source_highlight = next(
                        item for item in highlights if item.id == card.source_highlight_id
                    )
                    source_document = None
                if EvidenceService._matching_card_exists(
                    user=user,
                    profile=active_profile,
                    source_excerpt=card.source_excerpt,
                    title=card.title,
                ):
                    continue
                missing_details = EvidenceService._build_missing_details(
                    result=card.result,
                    metric=card.metric,
                    source_excerpt=card.source_excerpt,
                    initial=list(card.missing_details),
                )
                status = EvidenceStatus.NEEDS_DETAIL if missing_details else EvidenceStatus.DRAFT
                duplicate = EvidenceService._find_duplicate(
                    user=user,
                    profile=active_profile,
                    source_excerpt=card.source_excerpt,
                    title=card.title,
                )
                EvidenceCard.objects.create(
                    user=user,
                    profile=active_profile,
                    source_document=source_document,
                    source_highlight=source_highlight,
                    title=card.title,
                    problem=card.problem,
                    role=card.role,
                    action=card.action,
                    result=card.result,
                    metric=card.metric,
                    skills=card.skills,
                    competencies=card.competencies,
                    ownership_signal=card.ownership_signal,
                    constraints=card.constraints,
                    tradeoffs=card.tradeoffs,
                    missing_details=missing_details,
                    source_excerpt=card.source_excerpt,
                    source_location=card.source_location or "",
                    confidentiality=card.confidentiality_suggested,
                    status=status,
                    duplicate_of=duplicate,
                    duplicate_reason=(
                        card.duplicate_reason or ("Similar source excerpt." if duplicate else "")
                    ),
                    ai_generated_data=card.model_dump(mode="json"),
                )
                created_count += 1
            SprintWorkflowService.mark_evidence_review_started(
                user=user,
                sprint=sprint,
                has_reviewable_evidence=created_count > 0 or bool(highlights),
            )
        return created_count

    @staticmethod
    def save_card(
        *, user, sprint: InterviewSprint, card_id, cleaned_data: dict[str, Any]
    ) -> EvidenceCard:
        EvidenceService._require_evidence_review_mutable(user=user, sprint=sprint)
        card = EvidenceService.get_owned_card(user=user, sprint=sprint, card_id=card_id)
        if card.status == EvidenceStatus.REJECTED:
            raise EvidenceError("Rejected evidence cannot be edited. Extract or create a new card.")
        for field in CARD_EDITABLE_FIELDS:
            if field == "skills":
                value = cleaned_data.get("skills_text", [])
            elif field == "competencies":
                value = cleaned_data.get("competencies_text", [])
            elif field == "missing_details":
                value = cleaned_data.get("missing_details_text", [])
            else:
                value = cleaned_data.get(field)
            setattr(card, field, value)
        card.missing_details = EvidenceService._build_missing_details(
            result=card.result,
            metric=card.metric,
            source_excerpt=card.source_excerpt,
            initial=card.missing_details,
        )
        card.status = EvidenceStatus.NEEDS_DETAIL if card.missing_details else EvidenceStatus.DRAFT
        edited_data = {**card.user_edited_data, "edited": True}
        if cleaned_data.get("metric_user_corrected"):
            edited_data["metric_user_corrected"] = True
        else:
            edited_data.pop("metric_user_corrected", None)
        card.user_edited_data = edited_data
        card.save(update_fields=[*CARD_EDITABLE_FIELDS, "status", "user_edited_data", "updated_at"])
        return card

    @staticmethod
    def approve_card(
        *, user, sprint: InterviewSprint, card_id, cleaned_data: dict[str, Any] | None = None
    ) -> EvidenceCard:
        EvidenceService._require_evidence_review_mutable(user=user, sprint=sprint)
        card = EvidenceService.get_owned_card(user=user, sprint=sprint, card_id=card_id)
        if cleaned_data is not None:
            card = EvidenceService.save_card(
                user=user, sprint=sprint, card_id=card_id, cleaned_data=cleaned_data
            )
        EvidenceService._validate_approvable(card)
        card.status = EvidenceStatus.APPROVED
        card.missing_details = []
        card.save(update_fields=["status", "missing_details", "updated_at"])
        return card

    @staticmethod
    def reject_card(*, user, sprint: InterviewSprint, card_id) -> EvidenceCard:
        EvidenceService._require_evidence_review_mutable(user=user, sprint=sprint)
        card = EvidenceService.get_owned_card(user=user, sprint=sprint, card_id=card_id)
        card.status = EvidenceStatus.REJECTED
        card.save(update_fields=["status", "updated_at"])
        return card

    @staticmethod
    def approve_evidence_set(*, user, sprint: InterviewSprint) -> EvidenceThresholdResult:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        threshold = EvidenceService.evaluate_threshold(user=user, sprint=sprint)
        SprintWorkflowService.mark_evidence_approved(
            user=user,
            sprint=sprint,
            threshold_met=threshold.is_met,
        )
        return threshold

    @staticmethod
    def evaluate_threshold(*, user, sprint: InterviewSprint) -> EvidenceThresholdResult:
        EvidenceService._require_evidence_stage_readable(user=user, sprint=sprint)
        cards = list(
            EvidenceCard.objects.select_related("source_document", "source_highlight").filter(
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            )
        )
        return EvidenceThresholdResult(
            approved_count=len(cards),
            clear_result_count=sum(1 for card in cards if EvidenceService._has_clear_result(card)),
            all_have_provenance=all(
                EvidenceService._source_excerpt_is_valid(card) for card in cards
            ),
            metrics_valid=all(EvidenceService._metric_is_valid(card) for card in cards),
        )

    @staticmethod
    def _require_evidence_stage_readable(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if sprint.state not in {
            SprintState.OPPORTUNITY_CONFIRMED,
            SprintState.EVIDENCE_REVIEW,
            SprintState.EVIDENCE_APPROVED,
            SprintState.STORIES_READY,
            SprintState.MATCHING_READY,
            SprintState.PREVIEW_READY,
        }:
            raise InvalidSprintTransition("Evidence review requires a confirmed opportunity.")
        if sprint.active_profile_id is None or sprint.active_resume_id is None:
            raise SprintTransitionConditionMissing("A confirmed profile and resume are required.")
        profile_is_confirmed = sprint.active_profile.confirmation_status == "CONFIRMED"
        if sprint.active_profile.user_id != user.id or not profile_is_confirmed:
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")
        if (
            sprint.active_resume.user_id != user.id
            or not sprint.active_resume.is_active
            or sprint.active_resume.parsing_status != DocumentParsingStatus.CONFIRMED
        ):
            raise SprintTransitionConditionMissing("A confirmed active resume is required.")
        EvidenceService._get_confirmed_opportunity(user=user, sprint=sprint)

    @staticmethod
    def _require_evidence_stage_ready(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        valid_states = {
            SprintState.OPPORTUNITY_CONFIRMED,
            SprintState.EVIDENCE_REVIEW,
            SprintState.EVIDENCE_APPROVED,
        }
        if sprint.state not in valid_states:
            raise InvalidSprintTransition("Evidence review requires a confirmed opportunity.")
        if sprint.active_profile_id is None or sprint.active_resume_id is None:
            raise SprintTransitionConditionMissing("A confirmed profile and resume are required.")
        profile_is_confirmed = sprint.active_profile.confirmation_status == "CONFIRMED"
        if sprint.active_profile.user_id != user.id or not profile_is_confirmed:
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")
        if (
            sprint.active_resume.user_id != user.id
            or not sprint.active_resume.is_active
            or sprint.active_resume.parsing_status != DocumentParsingStatus.CONFIRMED
        ):
            raise SprintTransitionConditionMissing("A confirmed active resume is required.")
        EvidenceService._get_confirmed_opportunity(user=user, sprint=sprint)

    @staticmethod
    def _require_evidence_review_mutable(*, user, sprint: InterviewSprint) -> None:
        EvidenceService._require_evidence_stage_ready(user=user, sprint=sprint)
        if sprint.state == SprintState.EVIDENCE_APPROVED:
            raise InvalidSprintTransition("Approved evidence cannot be edited in this stage.")

    @staticmethod
    def _get_confirmed_opportunity(*, user, sprint: InterviewSprint):
        opportunity = (
            sprint.opportunities.filter(
                sprint__user=user,
                confirmation_status=OpportunityStatus.CONFIRMED,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if opportunity is None:
            raise SprintTransitionConditionMissing("A confirmed opportunity is required.")
        return opportunity

    @staticmethod
    def _validate_approvable(card: EvidenceCard) -> None:
        if card.status == EvidenceStatus.STALE:
            raise EvidenceError("Stale evidence must be regenerated or recreated before approval.")
        if not card.source_excerpt.strip():
            raise EvidenceError("Approved evidence requires a source excerpt.")
        if not EvidenceService._source_excerpt_is_valid(card):
            raise EvidenceError("Source excerpt must come from the resume or highlight.")
        if card.metric and not EvidenceService._metric_is_valid(card):
            raise EvidenceError(
                "Metric must appear in the source or be saved as a user correction."
            )

    @staticmethod
    def _source_excerpt_is_valid(card: EvidenceCard) -> bool:
        excerpt = _normalize(card.source_excerpt)
        if not excerpt:
            return False
        if card.source_document_id:
            return excerpt in _normalize(card.source_document.cleaned_text)
        if card.source_highlight_id:
            if card.source_highlight.status != CareerHighlightStatus.ACTIVE:
                return False
            return excerpt in _normalize(
                " ".join(
                    [
                        card.source_highlight.title,
                        card.source_highlight.description,
                        card.source_highlight.metric or "",
                        card.source_highlight.source_note,
                    ]
                )
            )
        return False

    @staticmethod
    def _metric_is_valid(card: EvidenceCard) -> bool:
        if not card.metric:
            return True
        metric = _normalize(card.metric)
        if not metric:
            return True
        source = ""
        if card.source_document_id:
            source = card.source_document.cleaned_text
        elif card.source_highlight_id:
            source = " ".join(
                [
                    card.source_highlight.title,
                    card.source_highlight.description,
                    card.source_highlight.metric or "",
                    card.source_highlight.source_note,
                ]
            )
        if metric in _normalize(source):
            return True
        return bool(card.user_edited_data.get("metric_user_corrected"))

    @staticmethod
    def _has_clear_result(card: EvidenceCard) -> bool:
        return bool((card.result or "").strip() or (card.metric or "").strip())

    @staticmethod
    def _build_missing_details(
        *, result: str | None, metric: str | None, source_excerpt: str, initial: list[str]
    ) -> list[str]:
        prompts = list(initial or [])
        if not (result or "").strip() and not (metric or "").strip():
            prompt = "Add the result or impact this evidence produced."
            if prompt not in prompts:
                prompts.append(prompt)
        if not source_excerpt.strip():
            prompt = "Add the source excerpt for this evidence."
            if prompt not in prompts:
                prompts.append(prompt)
        return prompts

    @staticmethod
    def _matching_card_exists(*, user, profile, source_excerpt: str, title: str) -> bool:
        normalized_excerpt = _normalize(source_excerpt)
        normalized_title = _normalize(title)
        cards = EvidenceCard.objects.filter(user=user, profile=profile).exclude(
            status=EvidenceStatus.STALE
        )
        for card in cards:
            if _normalize(card.source_excerpt) == normalized_excerpt:
                return True
            title_matches = _normalize(card.title) == normalized_title
            excerpt_contains_new = normalized_excerpt in _normalize(card.source_excerpt)
            if title_matches and excerpt_contains_new:
                return True
        return False

    @staticmethod
    def _find_duplicate(*, user, profile, source_excerpt: str, title: str) -> EvidenceCard | None:
        normalized_title = _normalize(title)
        cards = EvidenceCard.objects.filter(user=user, profile=profile).exclude(
            status=EvidenceStatus.STALE
        )
        for card in cards:
            title_matches = _normalize(card.title) == normalized_title
            excerpt_matches = _normalize(card.source_excerpt) == _normalize(source_excerpt)
            if title_matches or excerpt_matches:
                return card
        return None


def _normalize(value: str | None) -> str:
    return " ".join((value or "").casefold().split())
