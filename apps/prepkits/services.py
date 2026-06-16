from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from ai.schemas.preview import PROHIBITED_OUTCOME_PATTERN
from ai.services import EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.matching.models import StoryMatch
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.opportunities.role_packs import get_role_pack, role_pack_as_prompt_context
from apps.payments.models import Payment, PaymentStatus
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
from apps.previews.services import ReadinessPreviewService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryStatus

NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")


class PrepKitError(ValueError):
    """Raised when a Prep Kit cannot be generated or displayed safely."""


def _collect_text(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_collect_text(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_collect_text(item))
        return values
    if isinstance(value, str):
        return [value]
    return []


def _grounding_text_from_values(*values: object) -> str:
    return " ".join(_collect_text(list(values))).casefold()


@dataclass(frozen=True)
class PrepKitService:
    @staticmethod
    def current_prepkit(*, user, sprint: InterviewSprint) -> PrepKit | None:
        PrepKitService._require_paid_access(user=user, sprint=sprint)
        prepkit = (
            PrepKit.objects.filter(sprint=sprint, sprint__user=user, status=PrepKitStatus.READY)
            .order_by("-generated_at", "-created_at", "-id")
            .first()
        )
        if prepkit is None:
            return None
        try:
            current_revision = PrepKitService.current_input_revision(user=user, sprint=sprint)
        except (InvalidSprintTransition, SprintOwnershipError, SprintTransitionConditionMissing):
            PrepKitService.mark_stale_for_sprint(user=user, sprint=sprint)
            prepkit.refresh_from_db()
            return None
        if prepkit.input_revision != current_revision:
            PrepKitService.mark_stale_for_sprint(
                user=user, sprint=sprint, exclude_input_revision=current_revision
            )
            prepkit.refresh_from_db()
            return None
        return prepkit

    @staticmethod
    def latest_available_prepkit(*, user, sprint: InterviewSprint) -> PrepKit | None:
        PrepKitService._require_paid_access(user=user, sprint=sprint)
        return (
            PrepKit.objects.filter(
                sprint=sprint,
                sprint__user=user,
                status__in=[PrepKitStatus.READY, PrepKitStatus.STALE],
            )
            .order_by("-generated_at", "-created_at", "-id")
            .first()
        )

    @staticmethod
    def mark_stale_for_sprint(
        *, user, sprint: InterviewSprint, exclude_input_revision: str | None = None
    ) -> int:
        PrepKitService._require_owned_access(user=user, sprint=sprint)
        queryset = PrepKit.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status__in=[PrepKitStatus.PENDING, PrepKitStatus.READY],
        )
        if exclude_input_revision:
            queryset = queryset.exclude(input_revision=exclude_input_revision)
        return queryset.update(status=PrepKitStatus.STALE, updated_at=timezone.now())

    @staticmethod
    def latest_prepkit(*, user, sprint: InterviewSprint) -> PrepKit | None:
        PrepKitService._require_owned_access(user=user, sprint=sprint)
        return (
            PrepKit.objects.filter(sprint=sprint, sprint__user=user)
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def generate_prepkit(
        *,
        user,
        sprint: InterviewSprint,
        ai_service: EvidraAIService | None = None,
        force: bool = False,
    ) -> PrepKit:
        PrepKitService._require_paid_access(user=user, sprint=sprint)
        context = PrepKitService._generation_context(user=user, sprint=sprint)
        input_revision = PrepKitService.build_input_revision(sprint=sprint, **context)
        existing = PrepKitService.current_prepkit(user=user, sprint=sprint)
        if existing and existing.input_revision == input_revision and not force:
            return existing

        service = ai_service or EvidraAIService()
        prepkit = PrepKitService._get_or_create_pending_prepkit(
            user=user, sprint=sprint, input_revision=input_revision, force=force
        )
        payload = PrepKitService._prepkit_payload(**context)
        try:
            analysis = service.generate_prepkit_analysis(**payload)
            PrepKitService._validate_output(
                output=analysis,
                matches=context["matches"],
                stories=context["stories"],
                evidence=context["evidence"],
                grounding_payload=payload,
            )
            artifact = service.generate_prepkit_artifact(
                **payload, analysis=analysis.model_dump()
            )
            PrepKitService._validate_output(
                output=artifact,
                matches=context["matches"],
                stories=context["stories"],
                evidence=context["evidence"],
                grounding_payload={**payload, "analysis": analysis.model_dump()},
            )
        except Exception as exc:
            PrepKitService.mark_failed(
                prepkit=prepkit,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        with transaction.atomic():
            PrepKit.objects.select_for_update().filter(
                sprint=sprint,
                sprint__user=user,
                status__in=[PrepKitStatus.PENDING, PrepKitStatus.READY],
            ).exclude(pk=prepkit.pk).update(status=PrepKitStatus.STALE)
            locked = PrepKit.objects.select_for_update().get(pk=prepkit.pk, sprint__user=user)
            locked.role_briefing = artifact.role_briefing.model_dump()
            locked.fit_summary = artifact.fit_summary.model_dump()
            locked.competency_coverage = [
                item.model_dump() for item in artifact.competency_coverage
            ]
            locked.story_map = [item.model_dump() for item in artifact.story_map]
            locked.question_bank = [item.model_dump() for item in artifact.question_bank]
            locked.concern_map = [item.model_dump() for item in artifact.concern_map]
            locked.missing_evidence = [item.model_dump() for item in artifact.missing_evidence]
            locked.practice_priorities = [
                item.model_dump() for item in artifact.practice_priorities
            ]
            locked.seven_day_plan = [item.model_dump() for item in artifact.seven_day_plan]
            locked.interview_checklist = [
                item.model_dump() for item in artifact.interview_checklist
            ]
            locked.status = PrepKitStatus.READY
            locked.error_code = ""
            locked.error_message = ""
            locked.generated_at = timezone.now()
            locked.save()
            SprintWorkflowService.mark_prepkit_ready(user=user, sprint=sprint, prepkit=locked)
        return PrepKitService.current_prepkit(user=user, sprint=sprint) or prepkit

    @staticmethod
    def mark_failed(*, prepkit: PrepKit, error_code: str, error_message: str) -> None:
        PrepKit.objects.filter(pk=prepkit.pk, status=PrepKitStatus.PENDING).update(
            status=PrepKitStatus.FAILED,
            error_code=error_code[:64],
            error_message=error_message[:1000],
            updated_at=timezone.now(),
        )

    @staticmethod
    def build_input_revision(
        *, sprint: InterviewSprint, opportunity, preview, matches, stories, evidence
    ) -> str:
        payload = {
            "sprint_id": sprint.id,
            "active_profile_id": sprint.active_profile_id,
            "opportunity": [opportunity.id, opportunity.updated_at.isoformat()],
            "preview": [preview.id, preview.updated_at.isoformat()],
            "matches": [[match.id, match.created_at.isoformat()] for match in matches],
            "stories": [[story.id, story.updated_at.isoformat()] for story in stories],
            "evidence": [[card.id, card.updated_at.isoformat()] for card in evidence],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def current_input_revision(*, user, sprint: InterviewSprint) -> str:
        PrepKitService._require_paid_access(user=user, sprint=sprint)
        context = PrepKitService._generation_context(user=user, sprint=sprint)
        return PrepKitService.build_input_revision(sprint=sprint, **context)

    @staticmethod
    def _get_or_create_pending_prepkit(
        *, user, sprint, input_revision: str, force: bool
    ) -> PrepKit:
        with transaction.atomic():
            PrepKit.objects.select_for_update().filter(
                sprint=sprint,
                sprint__user=user,
                status__in=[PrepKitStatus.PENDING, PrepKitStatus.READY],
            ).exclude(input_revision=input_revision).update(status=PrepKitStatus.STALE)
            if force:
                PrepKit.objects.select_for_update().filter(
                    sprint=sprint,
                    sprint__user=user,
                    input_revision=input_revision,
                    status=PrepKitStatus.PENDING,
                ).update(status=PrepKitStatus.FAILED, error_code="RETRY_REQUESTED")
            existing = (
                PrepKit.objects.select_for_update()
                .filter(
                    sprint=sprint,
                    sprint__user=user,
                    input_revision=input_revision,
                    status__in=[PrepKitStatus.PENDING, PrepKitStatus.READY],
                )
                .order_by("-created_at", "-id")
                .first()
            )
            if existing:
                return existing
            return PrepKit.objects.create(
                sprint=sprint, input_revision=input_revision, status=PrepKitStatus.PENDING
            )

    @staticmethod
    def _generation_context(*, user, sprint: InterviewSprint) -> dict[str, object]:
        opportunity = PrepKitService._get_confirmed_opportunity(user=user, sprint=sprint)
        preview = PrepKitService._get_ready_preview(user=user, sprint=sprint)
        matches = PrepKitService._matches(user=user, sprint=sprint)
        stories = PrepKitService._ready_stories(user=user, sprint=sprint)
        evidence = PrepKitService._approved_evidence(user=user, sprint=sprint)
        if not matches:
            raise SprintTransitionConditionMissing("Contextual matches are required for Prep Kit.")
        if not stories:
            raise SprintTransitionConditionMissing("Ready stories are required for Prep Kit.")
        if not evidence:
            raise SprintTransitionConditionMissing("Approved evidence is required for Prep Kit.")
        return {
            "opportunity": opportunity,
            "preview": preview,
            "matches": matches,
            "stories": stories,
            "evidence": evidence,
        }

    @staticmethod
    def _prepkit_payload(*, opportunity, preview, matches, stories, evidence) -> dict[str, Any]:
        role_pack = get_role_pack(opportunity.role_family)
        return {
            "opportunity_context": ReadinessPreviewService._opportunity_payload(opportunity),
            "role_pack": role_pack_as_prompt_context(role_pack),
            "matches": [ReadinessPreviewService._match_payload(match) for match in matches],
            "stories": [ReadinessPreviewService._story_payload(story) for story in stories],
            "approved_evidence": [
                ReadinessPreviewService._evidence_payload(card) for card in evidence
            ],
            "preview": {
                "id": preview.id,
                "role_summary": preview.role_summary,
                "competencies": preview.competencies,
                "strengths": preview.strengths,
                "gaps": preview.gaps,
                "evidence_completeness": preview.evidence_completeness,
                "story_coverage": preview.story_coverage,
                "matched_story_excerpt": preview.matched_story_excerpt,
            },
        }

    @staticmethod
    def _validate_output(*, output, matches, stories, evidence, grounding_payload) -> None:
        dumped = output.model_dump() if hasattr(output, "model_dump") else output
        match_ids = {match.id for match in matches}
        story_ids = {story.id for story in stories}
        evidence_ids = {card.id for card in evidence}
        for item in PrepKitService._iter_grounded_items(dumped):
            if not item.get("source_refs"):
                raise PrepKitError("Prep Kit output must preserve source references.")
            if not set(item.get("match_ids") or []).issubset(match_ids):
                raise PrepKitError("Prep Kit references an unknown match.")
            if not set(item.get("story_ids") or []).issubset(story_ids):
                raise PrepKitError("Prep Kit references an unknown story.")
            if not set(item.get("evidence_ids") or []).issubset(evidence_ids):
                raise PrepKitError("Prep Kit references unapproved evidence.")
            for id_field in ["recommended_story_id", "linked_story_id"]:
                value = item.get(id_field)
                if value is not None and int(value) not in story_ids:
                    raise PrepKitError("Prep Kit references an unknown recommended story.")
            for ref in item.get("source_refs") or []:
                PrepKitService._validate_source_ref(
                    ref=ref,
                    match_ids=match_ids,
                    story_ids=story_ids,
                    evidence_ids=evidence_ids,
                    grounding_payload=grounding_payload,
                )
        narrative = " ".join(_collect_text(dumped))
        if PROHIBITED_OUTCOME_PATTERN.search(narrative):
            raise PrepKitError("Prep Kit must not include outcome guarantees.")
        grounding_text = _grounding_text_from_values(grounding_payload)
        for numeric_claim in NUMERIC_CLAIM_PATTERN.finditer(narrative):
            if numeric_claim.group(0).casefold() not in grounding_text:
                raise PrepKitError("Prep Kit contains an unsupported numeric claim.")

    @staticmethod
    def _validate_source_ref(
        *,
        ref: dict,
        match_ids: set[int],
        story_ids: set[int],
        evidence_ids: set[int],
        grounding_payload,
    ) -> None:
        source_type = ref.get("source_type")
        source_id = ref.get("source_id")
        if source_type == "match":
            if source_id is None or int(source_id) not in match_ids:
                raise PrepKitError("Prep Kit references an unknown match.")
            return
        if source_type == "story":
            if source_id is None or int(source_id) not in story_ids:
                raise PrepKitError("Prep Kit references an unknown story.")
            return
        if source_type == "evidence":
            if source_id is None or int(source_id) not in evidence_ids:
                raise PrepKitError("Prep Kit references unapproved evidence.")
            return
        source_values = PrepKitService._source_payload_values(
            source_type=source_type, grounding_payload=grounding_payload
        )
        if not source_values:
            raise PrepKitError("Prep Kit source reference points to missing source material.")
        source_field = ref.get("source_field")
        excerpt = ref.get("excerpt")
        if not source_field and not excerpt:
            raise PrepKitError("Prep Kit source reference must identify source material.")
        if source_field and source_field not in source_values:
            raise PrepKitError("Prep Kit source reference points to an unknown field.")
        if excerpt:
            source_text = _grounding_text_from_values(source_values)
            if excerpt.casefold() not in source_text:
                raise PrepKitError("Prep Kit source excerpt is not grounded in the source.")

    @staticmethod
    def _source_payload_values(*, source_type: str | None, grounding_payload) -> dict[str, object]:
        if source_type == "opportunity":
            return grounding_payload.get("opportunity_context") or {}
        if source_type == "company_context":
            return (grounding_payload.get("opportunity_context") or {}).get("company_context") or {}
        if source_type == "role_pack":
            return grounding_payload.get("role_pack") or {}
        if source_type == "preview":
            return grounding_payload.get("preview") or {}
        raise PrepKitError("Prep Kit source reference type is invalid.")

    @staticmethod
    def _iter_grounded_items(value: object):
        if isinstance(value, dict):
            if "source_refs" in value:
                yield value
            for item in value.values():
                yield from PrepKitService._iter_grounded_items(item)
        elif isinstance(value, list):
            for item in value:
                yield from PrepKitService._iter_grounded_items(item)

    @staticmethod
    def _require_owned_access(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

    @staticmethod
    def require_paid_access(*, user, sprint: InterviewSprint) -> Payment:
        return PrepKitService._require_paid_access(user=user, sprint=sprint)

    @staticmethod
    def _require_paid_access(*, user, sprint: InterviewSprint) -> Payment:
        PrepKitService._require_owned_access(user=user, sprint=sprint)
        if SprintState(sprint.state) not in {SprintState.PAID, SprintState.PREPKIT_READY}:
            raise InvalidSprintTransition(f"Cannot use Prep Kit while Sprint is in {sprint.state}.")
        payment = (
            Payment.objects.filter(user=user, sprint=sprint, status=PaymentStatus.PAID)
            .order_by("-paid_at", "-id")
            .first()
        )
        if (
            payment is None
            or not payment.provider_order_id
            or not payment.provider_payment_id
            or payment.paid_at is None
        ):
            raise SprintTransitionConditionMissing("Verified payment is required for Prep Kit.")
        SprintWorkflowService._validate_expected_payment_terms(payment=payment)
        return payment

    @staticmethod
    def _get_confirmed_opportunity(*, user, sprint: InterviewSprint) -> Opportunity:
        opportunity = (
            Opportunity.objects.filter(
                sprint=sprint, sprint__user=user, confirmation_status=OpportunityStatus.CONFIRMED
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if opportunity is None or not opportunity.jd_analysis:
            raise SprintTransitionConditionMissing("A confirmed analyzed opportunity is required.")
        return opportunity

    @staticmethod
    def _get_ready_preview(*, user, sprint: InterviewSprint) -> ReadinessPreview:
        preview = (
            ReadinessPreview.objects.filter(
                sprint=sprint, sprint__user=user, status=ReadinessPreviewStatus.READY
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if preview is None:
            raise SprintTransitionConditionMissing("A ready preview is required for Prep Kit.")
        return preview

    @staticmethod
    def _matches(*, user, sprint: InterviewSprint) -> list[StoryMatch]:
        return list(
            StoryMatch.objects.select_related(
                "primary_story", "alternative_story", "selected_story"
            )
            .filter(sprint=sprint, sprint__user=user)
            .order_by("competency_key")
        )

    @staticmethod
    def _ready_stories(*, user, sprint: InterviewSprint) -> list[Story]:
        return list(
            Story.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status__in=[StoryStatus.READY, StoryStatus.EDITED],
                source_story__isnull=True,
            ).order_by("-quality_score", "-updated_at", "-id")
        )

    @staticmethod
    def _approved_evidence(*, user, sprint: InterviewSprint) -> list[EvidenceCard]:
        return list(
            EvidenceCard.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            ).order_by("-updated_at", "-id")
        )
