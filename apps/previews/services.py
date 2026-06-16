from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from ai.schemas.preview import PROHIBITED_OUTCOME_PATTERN, ReadinessPreviewOutput
from ai.services import EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.matching.models import StoryMatch
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.opportunities.role_packs import get_role_pack, role_pack_as_prompt_context
from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryStatus

NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")


class ReadinessPreviewError(ValueError):
    """Raised when a readiness preview cannot be generated safely."""


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


def _text_values(value: object) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_text_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_text_values(item))
    elif isinstance(value, str):
        values.append(value)
    return values


@dataclass(frozen=True)
class ReadinessPreviewService:
    @staticmethod
    def current_preview(*, user, sprint: InterviewSprint) -> ReadinessPreview | None:
        ReadinessPreviewService._require_preview_stage(
            user=user, sprint=sprint, allow_matching_ready=True
        )
        return (
            ReadinessPreview.objects.filter(
                sprint=sprint,
                sprint__user=user,
                status=ReadinessPreviewStatus.READY,
            )
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def generate_preview(
        *,
        user,
        sprint: InterviewSprint,
        ai_service: EvidraAIService | None = None,
        force: bool = False,
    ) -> ReadinessPreview:
        ReadinessPreviewService._require_preview_stage(
            user=user, sprint=sprint, allow_matching_ready=True
        )
        opportunity = ReadinessPreviewService._get_confirmed_opportunity(user=user, sprint=sprint)
        matches = ReadinessPreviewService._matches(user=user, sprint=sprint)
        if not matches:
            raise SprintTransitionConditionMissing("Contextual matches are required for preview.")
        stories = ReadinessPreviewService._ready_stories(user=user, sprint=sprint)
        approved_evidence = ReadinessPreviewService._approved_evidence(user=user, sprint=sprint)
        if not stories:
            raise SprintTransitionConditionMissing("Ready stories are required for preview.")
        if not approved_evidence:
            raise SprintTransitionConditionMissing("Approved evidence is required for preview.")
        excerpt_match = ReadinessPreviewService._excerpt_match(matches=matches)
        if excerpt_match is None:
            raise SprintTransitionConditionMissing(
                "A credible matched story is required for preview."
            )

        input_revision = ReadinessPreviewService.build_input_revision(
            sprint=sprint,
            opportunity=opportunity,
            matches=matches,
            stories=stories,
            evidence=approved_evidence,
        )
        existing = ReadinessPreviewService.current_preview(user=user, sprint=sprint)
        if existing and existing.input_revision == input_revision and not force:
            return existing

        role_pack = get_role_pack(opportunity.role_family)
        payload = ReadinessPreviewService._preview_payload(
            opportunity=opportunity,
            role_pack=role_pack_as_prompt_context(role_pack),
            matches=matches,
            stories=stories,
            approved_evidence=approved_evidence,
            excerpt_match=excerpt_match,
        )
        service = ai_service or EvidraAIService()
        output = service.generate_preview(**payload)
        ReadinessPreviewService._validate_output_references(
            output=output,
            matches=matches,
            stories=stories,
            evidence=approved_evidence,
            grounding_payload=payload,
        )
        data = {
            "sprint": sprint,
            "role_summary": output.role_summary,
            "competencies": [item.model_dump() for item in output.competencies],
            "strengths": [item.model_dump() for item in output.strengths],
            "gaps": [item.model_dump() for item in output.gaps],
            "evidence_completeness": output.evidence_completeness.model_dump(),
            "story_coverage": output.story_coverage.model_dump(),
            "matched_story_excerpt": output.matched_story_excerpt.model_dump(),
            "prepkit_explanation": output.prepkit_explanation,
            "input_revision": input_revision,
            "status": ReadinessPreviewStatus.READY,
        }
        with transaction.atomic():
            replacing_existing_preview = existing and (
                force or existing.input_revision != input_revision
            )
            if replacing_existing_preview:
                ReadinessPreview.objects.select_for_update().filter(
                    sprint=sprint,
                    sprint__user=user,
                    status=ReadinessPreviewStatus.READY,
                ).update(status=ReadinessPreviewStatus.STALE)
            preview, created = ReadinessPreview.objects.select_for_update().get_or_create(
                sprint=sprint,
                input_revision=input_revision,
                status=ReadinessPreviewStatus.READY,
                defaults=data,
            )
            if not created and force:
                for key, value in data.items():
                    if key != "sprint":
                        setattr(preview, key, value)
                preview.save()
            ReadinessPreviewService._mark_prepkit_stale(user=user, sprint=sprint)
            SprintWorkflowService.mark_preview_ready(user=user, sprint=sprint, preview=preview)
        return ReadinessPreviewService.current_preview(user=user, sprint=sprint) or preview

    @staticmethod
    def _mark_prepkit_stale(*, user, sprint: InterviewSprint) -> None:
        from apps.prepkits.services import PrepKitService

        PrepKitService.mark_stale_for_sprint(user=user, sprint=sprint)

    @staticmethod
    def build_input_revision(
        *, sprint: InterviewSprint, opportunity: Opportunity, matches, stories, evidence
    ) -> str:
        payload = {
            "sprint_id": sprint.id,
            "active_profile_id": sprint.active_profile_id,
            "opportunity": [opportunity.id, opportunity.updated_at.isoformat()],
            "matches": [[m.id, m.created_at.isoformat()] for m in matches],
            "stories": [[s.id, s.updated_at.isoformat()] for s in stories],
            "evidence": [[e.id, e.updated_at.isoformat()] for e in evidence],
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _preview_payload(
        *, opportunity, role_pack, matches, stories, approved_evidence, excerpt_match
    ):
        selected_story = excerpt_match.selected_story or excerpt_match.primary_story
        return {
            "opportunity_context": ReadinessPreviewService._opportunity_payload(opportunity),
            "role_pack": role_pack,
            "matches": [ReadinessPreviewService._match_payload(match) for match in matches],
            "stories": [ReadinessPreviewService._story_payload(story) for story in stories],
            "approved_evidence": [
                ReadinessPreviewService._evidence_payload(card) for card in approved_evidence
            ],
            "matched_story_excerpt_source": {
                "match_id": excerpt_match.id,
                "story_id": selected_story.id,
                "title": selected_story.title,
                "excerpt": selected_story.short_answer[:700],
                "evidence_ids": [
                    evidence_id
                    for evidence_id in selected_story.evidence_ids
                    if evidence_id in {card.id for card in approved_evidence}
                ],
            },
            "deterministic_counts": ReadinessPreviewService._deterministic_counts(
                matches=matches, stories=stories, evidence=approved_evidence
            ),
        }

    @staticmethod
    def _deterministic_counts(*, matches, stories, evidence):
        matched = [match for match in matches if match.primary_story_id]
        gaps = [match for match in matches if not match.primary_story_id]
        result_backed = [card for card in evidence if card.result or card.metric]
        competencies_with_evidence = {
            match.competency_key
            for match in matches
            if match.evidence_ids or match.primary_story_id
        }
        return {
            "approved_evidence_count": len(evidence),
            "result_backed_evidence_count": len(result_backed),
            "competencies_with_evidence_count": len(competencies_with_evidence),
            "ready_story_count": len(stories),
            "matched_competency_count": len(matched),
            "gap_competency_count": len(gaps),
        }

    @staticmethod
    def _validate_output_references(
        *, output: ReadinessPreviewOutput, matches, stories, evidence, grounding_payload
    ):
        match_ids = {match.id for match in matches}
        story_ids = {story.id for story in stories}
        evidence_ids = {card.id for card in evidence}
        for item in [*output.competencies, *output.strengths, *output.gaps]:
            if item.source_match_id is not None and item.source_match_id not in match_ids:
                raise ReadinessPreviewError("Preview references an unknown match.")
            if not set(item.story_ids).issubset(story_ids):
                raise ReadinessPreviewError("Preview references an unknown story.")
            if not set(item.evidence_ids).issubset(evidence_ids):
                raise ReadinessPreviewError("Preview references unapproved evidence.")
        excerpt = output.matched_story_excerpt
        if excerpt.match_id not in match_ids or excerpt.story_id not in story_ids:
            raise ReadinessPreviewError("Preview excerpt references unknown source records.")
        if not set(excerpt.evidence_ids).issubset(evidence_ids):
            raise ReadinessPreviewError("Preview excerpt references unapproved evidence.")
        if len(output.competencies) != 5 or len(output.strengths) != 3 or len(output.gaps) != 3:
            raise ReadinessPreviewError(
                "Preview must include five competencies, three strengths, and three gaps."
            )
        grounding_text = _grounding_text_from_values(grounding_payload)
        narrative_text = ReadinessPreviewService._preview_narrative_text(output)
        if PROHIBITED_OUTCOME_PATTERN.search(narrative_text):
            raise ReadinessPreviewError("Preview must not include offer-probability claims.")
        for numeric_claim in NUMERIC_CLAIM_PATTERN.finditer(narrative_text):
            if numeric_claim.group(0).casefold() not in grounding_text:
                raise ReadinessPreviewError("Preview contains an unsupported numeric claim.")

    @staticmethod
    def _preview_narrative_text(output: ReadinessPreviewOutput) -> str:
        parts = [
            output.role_summary,
            output.prepkit_explanation,
            output.evidence_completeness.summary,
            output.story_coverage.summary,
            output.matched_story_excerpt.title,
            output.matched_story_excerpt.excerpt,
        ]
        for competency in output.competencies:
            parts.append(competency.label)
        for strength in output.strengths:
            parts.extend([strength.title, strength.explanation])
        for gap in output.gaps:
            parts.extend([gap.title, gap.explanation, gap.recommended_next_step or ""])
        return " ".join(parts)

    @staticmethod
    def _require_preview_stage(
        *, user, sprint: InterviewSprint, allow_matching_ready: bool
    ) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        allowed = {SprintState.PREVIEW_READY}
        if allow_matching_ready:
            allowed.add(SprintState.MATCHING_READY)
        if SprintState(sprint.state) not in allowed:
            raise InvalidSprintTransition(f"Cannot use preview while Sprint is in {sprint.state}.")
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

    @staticmethod
    def _excerpt_match(*, matches: list[StoryMatch]) -> StoryMatch | None:
        credible = [match for match in matches if match.selected_story_id or match.primary_story_id]
        if not credible:
            return None
        return sorted(credible, key=lambda match: (match.total_score, match.id), reverse=True)[0]

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
        }

    @staticmethod
    def _match_payload(match: StoryMatch) -> dict[str, Any]:
        return {
            "id": match.id,
            "competency_key": match.competency_key,
            "competency_label": match.competency_label,
            "primary_story_id": match.primary_story_id,
            "alternative_story_id": match.alternative_story_id,
            "selected_story_id": match.selected_story_id,
            "total_score": match.total_score,
            "explanation": match.explanation,
            "jd_excerpt": match.jd_excerpt,
            "evidence_ids": match.evidence_ids,
            "missing_signal": match.missing_signal,
            "recommended_emphasis": match.recommended_emphasis,
            "user_selected": match.user_selected,
        }

    @staticmethod
    def _story_payload(story: Story) -> dict[str, Any]:
        return {
            "id": story.id,
            "title": story.title,
            "story_type": story.story_type,
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
