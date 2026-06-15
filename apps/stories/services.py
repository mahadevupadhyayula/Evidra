from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.http import Http404

from ai.services import AIStoryGenerationError, AIStoryScoringError, EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.evidence.services import EvidenceService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryGenerationFailure, StoryStatus


class StoryError(ValueError):
    """Raised when reusable stories cannot be generated or edited safely."""


NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")

STORY_EDITABLE_FIELDS = [
    "title",
    "story_type",
    "situation",
    "task",
    "action",
    "result",
    "learning",
    "short_answer",
    "ninety_second_answer",
    "detailed_answer",
]


@dataclass(frozen=True)
class StoryService:
    @staticmethod
    def list_stories(*, user, sprint: InterviewSprint):
        StoryService._require_story_stage_ready(user=user, sprint=sprint)
        stories = list(
            Story.objects.filter(user=user, profile=sprint.active_profile).exclude(
                status=StoryStatus.ARCHIVED
            )
        )
        StoryService._attach_evidence_references(user=user, sprint=sprint, stories=stories)
        return stories

    @staticmethod
    def get_owned_story(*, user, sprint: InterviewSprint, story_id) -> Story:
        StoryService._require_story_stage_ready(user=user, sprint=sprint)
        try:
            return Story.objects.get(pk=story_id, user=user, profile=sprint.active_profile)
        except Story.DoesNotExist as exc:
            raise Http404("Story not found.") from exc

    @staticmethod
    def approved_evidence_choices(*, user, sprint: InterviewSprint) -> list[tuple[int, str]]:
        StoryService._require_story_stage_ready(user=user, sprint=sprint)
        return [
            (card.id, card.title)
            for card in StoryService._approved_evidence(user=user, sprint=sprint)
        ]

    @staticmethod
    def generate_stories(
        *,
        user,
        sprint: InterviewSprint,
        ai_service: EvidraAIService | None = None,
    ) -> list[Story]:
        StoryService._require_story_stage_ready(user=user, sprint=sprint)
        existing = list(
            Story.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status__in=[StoryStatus.READY, StoryStatus.EDITED],
                source_story__isnull=True,
            ).order_by("created_at", "id")
        )
        if existing:
            SprintWorkflowService.mark_stories_ready(
                user=user,
                sprint=sprint,
                has_usable_stories=True,
            )
            return existing

        approved_evidence = StoryService._approved_evidence(user=user, sprint=sprint)
        StoryService._validate_evidence_threshold(user=user, sprint=sprint)
        evidence_payload = [StoryService._evidence_payload(card) for card in approved_evidence]
        profile = sprint.active_profile
        profile_context = {
            "current_role": profile.current_role,
            "current_company": profile.current_company,
            "skills": profile.skills,
            "positioning_summary": profile.positioning_summary,
        }
        service = ai_service or EvidraAIService()
        try:
            generated = service.generate_stories(
                approved_evidence=evidence_payload,
                profile_context=profile_context,
            )
            story_score_input = [story.model_dump(mode="json") for story in generated.stories]
            scored = service.score_stories(
                stories=story_score_input,
                approved_evidence=evidence_payload,
            )
        except (AIStoryGenerationError, AIStoryScoringError) as exc:
            StoryService.record_generation_failure(
                user=user,
                sprint=sprint,
                operation="generate",
                error_message=str(exc),
            )
            raise
        scores_by_id = {score.client_story_id: score for score in scored.scores}
        evidence_by_id = {card.id: card for card in approved_evidence}

        with transaction.atomic():
            created: list[Story] = []
            for generated_story in generated.stories:
                StoryService._validate_evidence_ids(
                    evidence_ids=generated_story.evidence_ids,
                    evidence_by_id=evidence_by_id,
                )
                StoryService._validate_numeric_claims(generated_story.model_dump(), evidence_by_id)
                score = scores_by_id[generated_story.client_story_id]
                missing_details = _dedupe(
                    [*generated_story.missing_details, *score.missing_details]
                )
                story = Story.objects.create(
                    user=user,
                    profile=sprint.active_profile,
                    title=generated_story.title,
                    story_type=generated_story.story_type or "",
                    situation=generated_story.situation,
                    task=generated_story.task,
                    action=generated_story.action,
                    result=generated_story.result,
                    learning=generated_story.learning,
                    short_answer=generated_story.short_answer,
                    ninety_second_answer=generated_story.ninety_second_answer,
                    detailed_answer=generated_story.detailed_answer,
                    competency_tags=generated_story.competency_tags,
                    seniority_signals=generated_story.seniority_signals,
                    evidence_ids=generated_story.evidence_ids,
                    specificity_score=score.specificity_score,
                    impact_score=score.impact_score,
                    ownership_score=score.ownership_score,
                    clarity_score=score.clarity_score,
                    quality_score=StoryService.calculate_quality_score(
                        specificity_score=score.specificity_score,
                        impact_score=score.impact_score,
                        ownership_score=score.ownership_score,
                        clarity_score=score.clarity_score,
                    ),
                    missing_details=missing_details,
                    status=StoryStatus.READY,
                    ai_generated_data={
                        "story": generated_story.model_dump(mode="json"),
                        "score": score.model_dump(mode="json"),
                    },
                )
                created.append(story)
            SprintWorkflowService.mark_stories_ready(
                user=user,
                sprint=sprint,
                has_usable_stories=bool(created or existing),
            )
            return created

    @staticmethod
    def save_story(
        *, user, sprint: InterviewSprint, story_id, cleaned_data: dict[str, Any]
    ) -> Story:
        story = StoryService.get_owned_story(user=user, sprint=sprint, story_id=story_id)
        evidence_by_id = {
            card.id: card for card in StoryService._approved_evidence(user=user, sprint=sprint)
        }
        evidence_ids = cleaned_data.get("evidence_ids") or []
        StoryService._validate_evidence_ids(
            evidence_ids=evidence_ids, evidence_by_id=evidence_by_id
        )
        for field in STORY_EDITABLE_FIELDS:
            setattr(story, field, cleaned_data.get(field))
        story.competency_tags = cleaned_data.get("competency_tags_text", [])
        story.seniority_signals = cleaned_data.get("seniority_signals_text", [])
        story.missing_details = cleaned_data.get("missing_details_text", [])
        story.evidence_ids = evidence_ids
        StoryService._validate_numeric_claims(
            StoryService._story_text_payload(story), evidence_by_id
        )
        story.status = StoryStatus.EDITED
        story.user_edited_data = {**story.user_edited_data, "edited": True}
        story.save(
            update_fields=[
                *STORY_EDITABLE_FIELDS,
                "competency_tags",
                "seniority_signals",
                "missing_details",
                "evidence_ids",
                "status",
                "user_edited_data",
                "updated_at",
            ]
        )
        StoryService._invalidate_matching_outputs(user=user, sprint=sprint)
        return story

    @staticmethod
    def regenerate_story(
        *, user, sprint: InterviewSprint, story_id, ai_service: EvidraAIService | None = None
    ) -> Story:
        source = StoryService.get_owned_story(user=user, sprint=sprint, story_id=story_id)
        evidence_by_id = {
            card.id: card for card in StoryService._approved_evidence(user=user, sprint=sprint)
        }
        StoryService._validate_evidence_ids(
            evidence_ids=source.evidence_ids, evidence_by_id=evidence_by_id
        )
        evidence_payload = [
            StoryService._evidence_payload(evidence_by_id[evidence_id])
            for evidence_id in source.evidence_ids
        ]
        profile = sprint.active_profile
        service = ai_service or EvidraAIService()
        try:
            generated = service.generate_stories(
                approved_evidence=evidence_payload,
                profile_context={
                    "current_role": profile.current_role,
                    "current_company": profile.current_company,
                    "skills": profile.skills,
                    "positioning_summary": profile.positioning_summary,
                    "source_story_title": source.title,
                },
            )
            generated_story = generated.stories[0]
            scores = service.score_stories(
                stories=[generated_story.model_dump(mode="json")],
                approved_evidence=evidence_payload,
            )
        except (AIStoryGenerationError, AIStoryScoringError) as exc:
            StoryService.record_generation_failure(
                user=user,
                sprint=sprint,
                operation="regenerate",
                error_message=str(exc),
            )
            raise
        score = scores.scores[0]
        StoryService._validate_evidence_ids(
            evidence_ids=generated_story.evidence_ids,
            evidence_by_id=evidence_by_id,
        )
        StoryService._validate_numeric_claims(generated_story.model_dump(), evidence_by_id)
        latest_revision = (
            Story.objects.filter(source_story=source).order_by("-revision_number", "-id").first()
        )
        base_revision = (
            latest_revision.revision_number if latest_revision else source.revision_number
        )
        revision_number = base_revision + 1
        with transaction.atomic():
            return Story.objects.create(
                user=user,
                profile=sprint.active_profile,
                title=generated_story.title,
                story_type=generated_story.story_type or "",
                situation=generated_story.situation,
                task=generated_story.task,
                action=generated_story.action,
                result=generated_story.result,
                learning=generated_story.learning,
                short_answer=generated_story.short_answer,
                ninety_second_answer=generated_story.ninety_second_answer,
                detailed_answer=generated_story.detailed_answer,
                competency_tags=generated_story.competency_tags,
                seniority_signals=generated_story.seniority_signals,
                evidence_ids=generated_story.evidence_ids,
                specificity_score=score.specificity_score,
                impact_score=score.impact_score,
                ownership_score=score.ownership_score,
                clarity_score=score.clarity_score,
                quality_score=StoryService.calculate_quality_score(
                    specificity_score=score.specificity_score,
                    impact_score=score.impact_score,
                    ownership_score=score.ownership_score,
                    clarity_score=score.clarity_score,
                ),
                missing_details=_dedupe([*generated_story.missing_details, *score.missing_details]),
                status=StoryStatus.DRAFT,
                source_story=source,
                revision_number=revision_number,
                ai_generated_data={
                    "story": generated_story.model_dump(mode="json"),
                    "score": score.model_dump(mode="json"),
                },
            )

    @staticmethod
    def _invalidate_matching_outputs(*, user, sprint: InterviewSprint) -> None:
        if sprint.state != SprintState.MATCHING_READY:
            return
        from apps.matching.models import StoryMatch

        with transaction.atomic():
            StoryMatch.objects.select_for_update().filter(sprint=sprint, sprint__user=user).delete()
            SprintWorkflowService.mark_matching_stale(user=user, sprint=sprint)

    @staticmethod
    def calculate_quality_score(
        *, specificity_score: int, impact_score: int, ownership_score: int, clarity_score: int
    ) -> int:
        return round((specificity_score + impact_score + ownership_score + clarity_score) / 4)

    @staticmethod
    def record_generation_failure(
        *, user, sprint: InterviewSprint, operation: str, error_message: str
    ) -> StoryGenerationFailure | None:
        if (
            not user.is_authenticated
            or sprint.user_id != user.id
            or sprint.active_profile_id is None
            or sprint.active_profile.user_id != user.id
        ):
            return None
        return StoryGenerationFailure.objects.create(
            user=user,
            profile=sprint.active_profile,
            operation=operation,
            error_message=error_message[:2000],
        )

    @staticmethod
    def _require_story_stage_ready(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if sprint.state not in {
            SprintState.EVIDENCE_APPROVED,
            SprintState.STORIES_READY,
            SprintState.MATCHING_READY,
        }:
            raise InvalidSprintTransition("Reusable stories require approved evidence.")
        if sprint.active_profile_id is None or sprint.active_resume_id is None:
            raise SprintTransitionConditionMissing("A confirmed profile and resume are required.")
        if (
            sprint.active_profile.user_id != user.id
            or sprint.active_profile.confirmation_status != "CONFIRMED"
        ):
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")
        if sprint.active_resume.user_id != user.id or not sprint.active_resume.is_active:
            raise SprintTransitionConditionMissing("A confirmed active resume is required.")

    @staticmethod
    def _approved_evidence(*, user, sprint: InterviewSprint) -> list[EvidenceCard]:
        return list(
            EvidenceCard.objects.select_related("source_document", "source_highlight").filter(
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            )
        )

    @staticmethod
    def _attach_evidence_references(*, user, sprint: InterviewSprint, stories: list[Story]) -> None:
        evidence_ids = {
            int(evidence_id)
            for story in stories
            for evidence_id in story.evidence_ids
            if str(evidence_id).isdigit()
        }
        evidence_by_id = {
            card.id: card
            for card in EvidenceCard.objects.filter(
                id__in=evidence_ids,
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            )
        }
        for story in stories:
            story.evidence_references = [
                evidence_by_id[evidence_id]
                for evidence_id in story.evidence_ids
                if evidence_id in evidence_by_id
            ]

    @staticmethod
    def _validate_evidence_threshold(*, user, sprint: InterviewSprint) -> None:
        threshold = EvidenceService.evaluate_threshold(user=user, sprint=sprint)
        if not threshold.is_met:
            raise StoryError("Approved evidence no longer meets the story generation threshold.")

    @staticmethod
    def _evidence_payload(card: EvidenceCard) -> dict[str, Any]:
        return {
            "id": card.id,
            "title": card.title,
            "problem": card.problem,
            "role": card.role,
            "action": card.action,
            "result": card.result,
            "metric": card.metric,
            "skills": card.skills,
            "competencies": card.competencies,
            "ownership_signal": card.ownership_signal,
            "constraints": card.constraints,
            "tradeoffs": card.tradeoffs,
            "source_excerpt": card.source_excerpt,
            "source_location": card.source_location,
        }

    @staticmethod
    def _validate_evidence_ids(
        *, evidence_ids: list[int], evidence_by_id: dict[int, EvidenceCard]
    ) -> None:
        if not evidence_ids:
            raise StoryError("Stories must reference approved evidence.")
        if set(evidence_ids) - set(evidence_by_id):
            raise StoryError("Stories may reference approved evidence only.")

    @staticmethod
    def _validate_numeric_claims(
        payload: dict[str, Any], evidence_by_id: dict[int, EvidenceCard]
    ) -> None:
        evidence_ids = [int(item) for item in payload.get("evidence_ids", [])]
        evidence_text = _normalize(
            " ".join(
                str(getattr(evidence_by_id[evidence_id], field) or "")
                for evidence_id in evidence_ids
                for field in [
                    "title",
                    "problem",
                    "role",
                    "action",
                    "result",
                    "metric",
                    "ownership_signal",
                    "constraints",
                    "tradeoffs",
                    "source_excerpt",
                ]
            )
        )
        for field in [
            "situation",
            "task",
            "action",
            "result",
            "learning",
            "short_answer",
            "ninety_second_answer",
            "detailed_answer",
        ]:
            value = payload.get(field)
            if value and _has_unsupported_numeric_claim(str(value), evidence_text):
                raise StoryError("Story numeric claims must trace to approved evidence.")

    @staticmethod
    def _story_text_payload(story: Story) -> dict[str, Any]:
        return {
            "situation": story.situation,
            "task": story.task,
            "action": story.action,
            "result": story.result,
            "learning": story.learning,
            "short_answer": story.short_answer,
            "ninety_second_answer": story.ninety_second_answer,
            "detailed_answer": story.detailed_answer,
            "evidence_ids": story.evidence_ids,
        }


def _normalize(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


def _has_unsupported_numeric_claim(value: str, normalized_source: str) -> bool:
    for match in NUMERIC_CLAIM_PATTERN.finditer(value):
        normalized_claim = _normalize(match.group(0))
        if normalized_claim and normalized_claim not in normalized_source:
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
