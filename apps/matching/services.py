from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.http import Http404

from ai.services import EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.matching.models import StoryMatch
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.opportunities.role_packs import get_role_pack, role_pack_as_prompt_context
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryStatus


class MatchingError(ValueError):
    """Raised when contextual matching cannot be generated or changed safely."""


WEIGHTS = {
    "competency_score": 0.30,
    "role_relevance_score": 0.25,
    "seniority_score": 0.15,
    "evidence_strength_score": 0.20,
    "company_context_score": 0.10,
}
NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")


def _grounding_text_from_values(*values: object) -> str:
    parts: list[str] = []

    def collect(value: object) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        parts.append(str(value))

    for value in values:
        collect(value)
    return " ".join(parts).casefold()


def _validate_narrative_numeric_claims(*, values: list[str | None], grounding_text: str) -> None:
    """Numeric match narrative claims must be grounded in the final story/evidence context.

    Non-numeric employer and achievement claims are constrained by the matching prompt and by
    preserving story/evidence/JD references rather than accepting free-floating source IDs.
    """
    for value in values:
        if not value:
            continue
        for numeric_claim in NUMERIC_CLAIM_PATTERN.finditer(value):
            if numeric_claim.group(0).casefold() not in grounding_text:
                raise MatchingError("Story match narrative contains an unsupported numeric claim.")


@dataclass(frozen=True)
class MatchingService:
    @staticmethod
    def list_matches(*, user, sprint: InterviewSprint) -> list[StoryMatch]:
        MatchingService._require_matching_stage_readable(user=user, sprint=sprint)
        return list(
            StoryMatch.objects.select_related(
                "primary_story", "alternative_story", "selected_story", "sprint"
            )
            .filter(sprint=sprint, sprint__user=user)
            .order_by("competency_key")
        )

    @staticmethod
    def generate_matches(
        *,
        user,
        sprint: InterviewSprint,
        ai_service: EvidraAIService | None = None,
        force: bool = False,
    ) -> list[StoryMatch]:
        MatchingService._require_matching_stage_ready(
            user=user, sprint=sprint, allow_stories_ready=True
        )
        existing = MatchingService.list_matches(user=user, sprint=sprint)
        if existing and sprint.state == SprintState.MATCHING_READY and not force:
            return existing

        opportunity = MatchingService._get_confirmed_opportunity(user=user, sprint=sprint)
        role_pack = get_role_pack(opportunity.role_family)
        competency_map = MatchingService.build_competency_map(role_pack.competencies)
        stories = MatchingService._ready_stories(user=user, sprint=sprint)
        if not stories:
            raise SprintTransitionConditionMissing(
                "Ready stories are required for contextual matching."
            )
        evidence_by_id = MatchingService._approved_evidence_by_id(user=user, sprint=sprint)
        story_payloads = [MatchingService._story_payload(story) for story in stories]
        evidence_payloads = [
            MatchingService._evidence_payload(card) for card in evidence_by_id.values()
        ]
        opportunity_payload = MatchingService._opportunity_payload(opportunity)
        service = ai_service or EvidraAIService()
        scored = service.score_story_matches(
            opportunity_context=opportunity_payload,
            role_pack=role_pack_as_prompt_context(role_pack),
            competency_map=competency_map,
            stories=story_payloads,
            approved_evidence=evidence_payloads,
        )
        matches_by_key = {match.competency_key: match for match in scored.matches}
        created_data: list[dict[str, Any]] = []
        previous_overrides = {
            match.competency_key: match.selected_story_id
            for match in existing
            if match.user_selected and match.selected_story_id
        }
        story_by_id = {story.id: story for story in stories}
        for competency in competency_map:
            candidate = matches_by_key.get(competency["key"])
            if candidate is None:
                created_data.append(
                    MatchingService._gap_data(
                        sprint=sprint,
                        competency_key=competency["key"],
                        competency_label=competency["label"],
                        missing_signal="No credible story was found for this competency.",
                    )
                )
                continue
            created_data.append(
                MatchingService._candidate_to_data(
                    sprint=sprint,
                    competency_label=competency["label"],
                    candidate=candidate,
                    story_by_id=story_by_id,
                    evidence_by_id=evidence_by_id,
                    job_description=opportunity.job_description,
                    previous_override_story_id=previous_overrides.get(competency["key"]),
                )
            )

        with transaction.atomic():
            StoryMatch.objects.select_for_update().filter(sprint=sprint, sprint__user=user).delete()
            created = [StoryMatch.objects.create(**data) for data in created_data]
            SprintWorkflowService.mark_matching_ready(
                user=user,
                sprint=sprint,
                has_matches_or_gaps=bool(created),
            )
        return MatchingService.list_matches(user=user, sprint=sprint)

    @staticmethod
    def set_user_override(
        *, user, sprint: InterviewSprint, match_id, story_id: int | None
    ) -> StoryMatch:
        MatchingService._require_matching_stage_ready(
            user=user, sprint=sprint, allow_stories_ready=False
        )
        try:
            match = StoryMatch.objects.select_related(
                "primary_story", "alternative_story", "selected_story"
            ).get(
                pk=match_id,
                sprint=sprint,
                sprint__user=user,
            )
        except StoryMatch.DoesNotExist as exc:
            raise Http404("Story match not found.") from exc
        if story_id is None:
            match.user_selected = False
            match.selected_story = None
            match.save(update_fields=["user_selected", "selected_story"])
            return match
        valid_story_ids = {
            sid for sid in [match.primary_story_id, match.alternative_story_id] if sid
        }
        if int(story_id) not in valid_story_ids:
            raise MatchingError("Select the primary or alternative story for this match.")
        match.selected_story_id = int(story_id)
        match.user_selected = True
        match.save(update_fields=["selected_story", "user_selected"])
        return match

    @staticmethod
    def calculate_total_score(
        *,
        competency_score: int,
        role_relevance_score: int,
        seniority_score: int,
        evidence_strength_score: int,
        company_context_score: int,
    ) -> int:
        total = round(
            competency_score * WEIGHTS["competency_score"]
            + role_relevance_score * WEIGHTS["role_relevance_score"]
            + seniority_score * WEIGHTS["seniority_score"]
            + evidence_strength_score * WEIGHTS["evidence_strength_score"]
            + company_context_score * WEIGHTS["company_context_score"]
        )
        return max(0, min(100, total))

    @staticmethod
    def build_competency_map(competencies: list[str]) -> list[dict[str, str]]:
        return [{"key": _slugify(item), "label": item} for item in competencies]

    @staticmethod
    def _candidate_to_data(
        *,
        sprint: InterviewSprint,
        competency_label: str,
        candidate,
        story_by_id: dict[int, Story],
        evidence_by_id: dict[int, EvidenceCard],
        job_description: str,
        previous_override_story_id: int | None,
    ) -> dict[str, Any]:
        primary_story = (
            story_by_id.get(candidate.primary_story_id) if candidate.primary_story_id else None
        )
        alternative_story = (
            story_by_id.get(candidate.alternative_story_id)
            if candidate.alternative_story_id
            else None
        )
        story_evidence_ids = set(primary_story.evidence_ids if primary_story else [])
        candidate_evidence_ids = [
            evidence_id for evidence_id in candidate.evidence_ids if evidence_id in evidence_by_id
        ]
        evidence_ids = [
            evidence_id
            for evidence_id in candidate_evidence_ids
            if evidence_id in story_evidence_ids
        ]
        if primary_story and not evidence_ids:
            evidence_ids = [
                evidence_id
                for evidence_id in primary_story.evidence_ids
                if evidence_id in evidence_by_id
            ]
        if primary_story and not set(evidence_ids).issubset(story_evidence_ids):
            return MatchingService._gap_data(
                sprint=sprint,
                competency_key=candidate.competency_key,
                competency_label=competency_label,
                missing_signal=candidate.missing_signal
                or "The suggested story lacks approved evidence for this competency.",
                jd_excerpt=candidate.jd_excerpt or "",
                recommended_emphasis=candidate.recommended_emphasis or "",
            )
        total_score = MatchingService.calculate_total_score(
            competency_score=candidate.competency_score,
            role_relevance_score=candidate.role_relevance_score,
            seniority_score=candidate.seniority_score,
            evidence_strength_score=candidate.evidence_strength_score,
            company_context_score=candidate.company_context_score,
        )
        if (
            primary_story is None
            or total_score < 50
            or candidate.evidence_strength_score < 40
            or candidate.competency_score < 40
        ):
            gap_grounding_text = _grounding_text_from_values(
                job_description,
                MatchingService._story_payload(primary_story) if primary_story else None,
                [
                    MatchingService._evidence_payload(evidence_by_id[evidence_id])
                    for evidence_id in evidence_ids
                ],
            )
            _validate_narrative_numeric_claims(
                values=[
                    candidate.explanation,
                    candidate.missing_signal,
                    candidate.recommended_emphasis,
                ],
                grounding_text=gap_grounding_text,
            )
            return MatchingService._gap_data(
                sprint=sprint,
                competency_key=candidate.competency_key,
                competency_label=competency_label,
                missing_signal=candidate.missing_signal
                or "No credible story was found for this competency.",
                jd_excerpt=candidate.jd_excerpt or "",
                recommended_emphasis=candidate.recommended_emphasis or "",
                scores=candidate,
            )
        if (
            candidate.jd_excerpt
            and candidate.jd_excerpt.casefold() not in job_description.casefold()
        ):
            raise MatchingError("JD excerpt must come from the confirmed job description.")
        grounding_text = _grounding_text_from_values(
            job_description,
            MatchingService._story_payload(primary_story),
            [
                MatchingService._evidence_payload(evidence_by_id[evidence_id])
                for evidence_id in evidence_ids
            ],
        )
        _validate_narrative_numeric_claims(
            values=[
                candidate.explanation,
                candidate.missing_signal,
                candidate.recommended_emphasis,
            ],
            grounding_text=grounding_text,
        )
        user_selected = previous_override_story_id is not None and previous_override_story_id in {
            primary_story.id if primary_story else None,
            alternative_story.id if alternative_story else None,
        }
        selected_story = story_by_id.get(previous_override_story_id) if user_selected else None
        return {
            "sprint": sprint,
            "competency_key": candidate.competency_key,
            "competency_label": competency_label,
            "primary_story": primary_story,
            "alternative_story": alternative_story,
            "selected_story": selected_story,
            "competency_score": candidate.competency_score,
            "role_relevance_score": candidate.role_relevance_score,
            "seniority_score": candidate.seniority_score,
            "evidence_strength_score": candidate.evidence_strength_score,
            "company_context_score": candidate.company_context_score,
            "total_score": total_score,
            "explanation": _remove_low_fit_strong_language(candidate.explanation, total_score),
            "jd_excerpt": candidate.jd_excerpt or "",
            "evidence_ids": evidence_ids,
            "missing_signal": candidate.missing_signal or "",
            "recommended_emphasis": candidate.recommended_emphasis or "",
            "user_selected": user_selected,
        }

    @staticmethod
    def _gap_data(
        *,
        sprint: InterviewSprint,
        competency_key: str,
        competency_label: str,
        missing_signal: str,
        jd_excerpt: str = "",
        recommended_emphasis: str = "",
        scores=None,
    ) -> dict[str, Any]:
        return {
            "sprint": sprint,
            "competency_key": competency_key,
            "competency_label": competency_label,
            "primary_story": None,
            "alternative_story": None,
            "selected_story": None,
            "competency_score": getattr(scores, "competency_score", 0),
            "role_relevance_score": getattr(scores, "role_relevance_score", 0),
            "seniority_score": getattr(scores, "seniority_score", 0),
            "evidence_strength_score": getattr(scores, "evidence_strength_score", 0),
            "company_context_score": getattr(scores, "company_context_score", 0),
            "total_score": 0,
            "explanation": "",
            "jd_excerpt": jd_excerpt,
            "evidence_ids": [],
            "missing_signal": missing_signal,
            "recommended_emphasis": recommended_emphasis,
            "user_selected": False,
        }

    @staticmethod
    def _require_matching_stage_readable(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if SprintState(sprint.state) not in {
            SprintState.STORIES_READY,
            SprintState.MATCHING_READY,
            SprintState.PREVIEW_READY,
        }:
            raise InvalidSprintTransition(f"Cannot use matching while Sprint is in {sprint.state}.")
        if sprint.active_profile_id is None:
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")

    @staticmethod
    def _require_matching_stage_ready(
        *, user, sprint: InterviewSprint, allow_stories_ready: bool
    ) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        allowed = {SprintState.MATCHING_READY}
        if allow_stories_ready:
            allowed.add(SprintState.STORIES_READY)
        if SprintState(sprint.state) not in allowed:
            raise InvalidSprintTransition(f"Cannot use matching while Sprint is in {sprint.state}.")
        if sprint.active_profile_id is None:
            raise SprintTransitionConditionMissing("A confirmed active profile is required.")

    @staticmethod
    def _get_confirmed_opportunity(*, user, sprint: InterviewSprint) -> Opportunity:
        opportunity = (
            Opportunity.objects.select_related("sprint")
            .filter(
                sprint=sprint, sprint__user=user, confirmation_status=OpportunityStatus.CONFIRMED
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if opportunity is None or not opportunity.jd_analysis:
            raise SprintTransitionConditionMissing("A confirmed analyzed opportunity is required.")
        return opportunity

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
    def _approved_evidence_by_id(*, user, sprint: InterviewSprint) -> dict[int, EvidenceCard]:
        return {
            card.id: card
            for card in EvidenceCard.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            )
        }

    @staticmethod
    def _story_payload(story: Story) -> dict[str, Any]:
        return {
            "id": story.id,
            "title": story.title,
            "story_type": story.story_type,
            "situation": story.situation,
            "task": story.task,
            "action": story.action,
            "result": story.result,
            "learning": story.learning,
            "short_answer": story.short_answer,
            "ninety_second_answer": story.ninety_second_answer,
            "detailed_answer": story.detailed_answer,
            "competency_tags": story.competency_tags,
            "seniority_signals": story.seniority_signals,
            "evidence_ids": story.evidence_ids,
            "quality_score": story.quality_score,
        }

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
            "competencies": card.competencies,
            "source_excerpt": card.source_excerpt,
            "source_location": card.source_location,
        }

    @staticmethod
    def _opportunity_payload(opportunity: Opportunity) -> dict[str, Any]:
        return {
            "role_title": opportunity.role_title,
            "role_family": opportunity.role_family,
            "target_seniority": opportunity.target_seniority,
            "company_name": opportunity.company_name,
            "job_description": opportunity.job_description,
            "interview_stage": opportunity.interview_stage,
            "concerns": opportunity.concerns,
            "improvement_goals": opportunity.improvement_goals,
            "jd_analysis": opportunity.jd_analysis,
            "company_context": opportunity.company_context,
            "company_context_status": opportunity.company_context_status,
        }


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return text or "competency"


def _remove_low_fit_strong_language(explanation: str, total_score: int) -> str:
    if total_score >= 80:
        return explanation
    return re.sub(r"\bstrong\b", "credible", explanation, flags=re.IGNORECASE)
