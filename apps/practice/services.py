from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from ai.services import AIAnswerEvaluationError, EvidraAIService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.practice.models import PracticeAttempt
from apps.prepkits.models import PrepKit
from apps.prepkits.services import PrepKitService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryStatus

NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")
PROPER_NOUN_PHRASE_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.-]+)(?:\s+(?:[A-Z][A-Za-z0-9&.-]+))*\b"
)
ALLOWED_CAPITALIZED_TERMS = {"I", "STAR", "CAR"}
ALLOWED_FEEDBACK_TERMS = {
    "a",
    "about",
    "also",
    "an",
    "and",
    "answer",
    "addresses",
    "as",
    "because",
    "by",
    "can",
    "clear",
    "clearly",
    "clearer",
    "context",
    "did",
    "during",
    "for",
    "from",
    "how",
    "i",
    "in",
    "into",
    "it",
    "my",
    "of",
    "on",
    "outcome",
    "question",
    "role",
    "so",
    "story",
    "that",
    "the",
    "then",
    "this",
    "through",
    "to",
    "using",
    "was",
    "we",
    "what",
    "when",
    "would",
    "where",
    "while",
    "with",
    "add",
    "adds",
    "better",
    "briefly",
    "claim",
    "claims",
    "connect",
    "could",
    "detail",
    "details",
    "emphasize",
    "example",
    "explain",
    "explained",
    "focus",
    "follow",
    "grounded",
    "improve",
    "improved",
    "include",
    "learn",
    "make",
    "more",
    "next",
    "selected",
    "specific",
    "strength",
    "strong",
    "support",
    "supported",
    "unsupported",
    "up",
    "you",
    "your",
}
CONTENT_TOKEN_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z-]{3,}\b")


class PracticeError(ValueError):
    """Raised when a practice attempt cannot be created safely."""


SCORE_FIELDS = [
    "relevance_score",
    "structure_score",
    "specificity_score",
    "ownership_score",
    "impact_score",
    "clarity_score",
]


def _collect_text(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(_collect_text(item))
        return items
    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(_collect_text(item))
        return items
    return [str(value)]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class PracticeService:
    @staticmethod
    def practice_context(*, user, sprint: InterviewSprint) -> dict[str, Any]:
        prepkit = None
        questions: list[dict[str, Any]] = []
        access_error = ""
        try:
            prepkit = PracticeService.current_practice_prepkit(user=user, sprint=sprint)
            questions = PracticeService.priority_questions(
                user=user, sprint=sprint, prepkit=prepkit
            )
        except (
            InvalidSprintTransition,
            SprintOwnershipError,
            SprintTransitionConditionMissing,
            PracticeError,
        ) as exc:
            access_error = str(exc)
        return {
            "sprint": sprint,
            "prepkit": prepkit,
            "questions": questions,
            "attempts": PracticeService.attempt_history(user=user, sprint=sprint),
            "access_error": access_error,
        }

    @staticmethod
    def current_practice_prepkit(*, user, sprint: InterviewSprint) -> PrepKit:
        PracticeService._require_owned_access(user=user, sprint=sprint)
        if SprintState(sprint.state) not in {
            SprintState.PREPKIT_READY,
            SprintState.PRACTICE_ACTIVE,
        }:
            raise InvalidSprintTransition(f"Cannot practice while Sprint is in {sprint.state}.")
        prepkit = PrepKitService.current_prepkit(user=user, sprint=sprint)
        if prepkit is None:
            raise SprintTransitionConditionMissing(
                "A current ready Prep Kit is required before practice."
            )
        if not prepkit.question_bank:
            raise PracticeError("The current Prep Kit does not include practice questions.")
        return prepkit

    @staticmethod
    def priority_questions(
        *, user, sprint: InterviewSprint, prepkit: PrepKit | None = None
    ) -> list[dict[str, Any]]:
        PracticeService._require_owned_access(user=user, sprint=sprint)
        prepkit = prepkit or PracticeService.current_practice_prepkit(user=user, sprint=sprint)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        questions: list[dict[str, Any]] = []
        for index, item in enumerate(prepkit.question_bank):
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            raw_priority = str(item.get("priority") or "medium").lower()
            priority = raw_priority if raw_priority in priority_order else "medium"
            question_id = str(item.get("id") or f"q{index + 1}")
            questions.append(
                {
                    "question_id": question_id,
                    "question": question,
                    "detail": item.get("detail") or "",
                    "priority": priority,
                    "recommended_story_id": item.get("recommended_story_id"),
                    "source_refs": item.get("source_refs") or [],
                    "evidence_ids": item.get("evidence_ids") or [],
                    "story_ids": item.get("story_ids") or [],
                    "match_ids": item.get("match_ids") or [],
                    "order": index,
                    "snapshot": item,
                }
            )
        questions.sort(key=lambda q: (priority_order[q["priority"]], q["order"]))
        return questions

    @staticmethod
    def submit_answer(
        *,
        user,
        sprint: InterviewSprint,
        question_id: str,
        answer_text: str,
        ai_service: EvidraAIService | None = None,
    ) -> PracticeAttempt:
        PracticeService._require_owned_access(user=user, sprint=sprint)
        answer = answer_text.strip()
        if len(answer) < 20:
            raise PracticeError("A text answer of at least 20 characters is required.")
        prepkit = PracticeService.current_practice_prepkit(user=user, sprint=sprint)
        questions = PracticeService.priority_questions(user=user, sprint=sprint, prepkit=prepkit)
        question = next((item for item in questions if item["question_id"] == question_id), None)
        if question is None:
            raise PracticeError("Choose a current practice question.")
        linked_story = PracticeService._linked_story(user=user, sprint=sprint, question=question)
        evidence = PracticeService._approved_evidence(
            user=user, sprint=sprint, question=question, linked_story=linked_story
        )
        payload = PracticeService._evaluation_payload(
            question=question, linked_story=linked_story, evidence=evidence, prepkit=prepkit
        )
        service = ai_service or EvidraAIService()
        try:
            output = service.evaluate_answer(answer_text=answer, **payload)
        except AIAnswerEvaluationError as exc:
            raise PracticeError(str(exc)) from exc
        PracticeService._validate_feedback_output(output, payload, answer)
        with transaction.atomic():
            locked_sprint = InterviewSprint.objects.select_for_update().get(pk=sprint.pk, user=user)
            previous = (
                PracticeAttempt.objects.select_for_update()
                .filter(sprint=locked_sprint, question_id=question_id)
                .order_by("-attempt_number")
                .first()
            )
            next_number = (previous.attempt_number if previous else 0) + 1
            comparison = PracticeService._comparison(output=output, previous=previous)
            feedback = {
                "strengths": output.strengths,
                "improvements": output.improvements,
                "unsupported_claims": [claim.model_dump() for claim in output.unsupported_claims],
                "source_refs": [ref.model_dump() for ref in output.source_refs],
                "comparison": comparison,
                "question_snapshot": question["snapshot"],
                "linked_story_snapshot": PracticeService._story_payload(linked_story)
                if linked_story
                else None,
            }
            attempt = PracticeAttempt.objects.create(
                sprint=locked_sprint,
                question_id=question_id,
                linked_story=linked_story,
                answer_text=answer,
                relevance_score=output.relevance_score,
                structure_score=output.structure_score,
                specificity_score=output.specificity_score,
                ownership_score=output.ownership_score,
                impact_score=output.impact_score,
                clarity_score=output.clarity_score,
                feedback=feedback,
                improved_answer=output.improved_answer,
                follow_up_question=output.follow_up_question,
                attempt_number=next_number,
            )
            SprintWorkflowService.mark_practice_active(
                user=user, sprint=locked_sprint, attempt=attempt
            )
            return attempt

    @staticmethod
    def attempt_history(
        *, user, sprint: InterviewSprint, question_id: str | None = None
    ) -> list[PracticeAttempt]:
        PracticeService._require_owned_access(user=user, sprint=sprint)
        queryset = PracticeAttempt.objects.select_related("linked_story").filter(
            sprint=sprint, sprint__user=user
        )
        if question_id:
            queryset = queryset.filter(question_id=question_id)
        return list(queryset.order_by("question_id", "-attempt_number", "-created_at"))

    @staticmethod
    def _linked_story(*, user, sprint: InterviewSprint, question: dict[str, Any]) -> Story | None:
        story_id = question.get("recommended_story_id")
        if story_id is None:
            return None
        story = Story.objects.filter(
            pk=story_id,
            user=user,
            profile=sprint.active_profile,
            status__in=[StoryStatus.READY, StoryStatus.EDITED],
        ).first()
        if story is None:
            raise PracticeError("The linked story for this practice question is no longer current.")
        return story

    @staticmethod
    def _approved_evidence(
        *, user, sprint: InterviewSprint, question: dict[str, Any], linked_story: Story | None
    ) -> list[EvidenceCard]:
        ids = {int(item) for item in question.get("evidence_ids") or [] if str(item).isdigit()}
        if linked_story:
            ids.update(int(item) for item in linked_story.evidence_ids if str(item).isdigit())
        queryset = EvidenceCard.objects.filter(
            user=user, profile=sprint.active_profile, status=EvidenceStatus.APPROVED
        )
        if ids:
            prioritized = list(queryset.filter(id__in=ids))
            if prioritized:
                return prioritized
            raise PracticeError(
                "Referenced evidence for this practice question is no longer current."
            )
        return list(queryset.order_by("-updated_at", "-id")[:5])

    @staticmethod
    def _evaluation_payload(
        *,
        question: dict[str, Any],
        linked_story: Story | None,
        evidence: list[EvidenceCard],
        prepkit: PrepKit,
    ) -> dict[str, Any]:
        return {
            "question": question,
            "linked_story": PracticeService._story_payload(linked_story) if linked_story else None,
            "approved_evidence": [PracticeService._evidence_payload(card) for card in evidence],
            "prepkit_context": {
                "id": prepkit.id,
                "input_revision": prepkit.input_revision,
                "practice_priorities": prepkit.practice_priorities,
            },
        }

    @staticmethod
    def _story_payload(story: Story | None) -> dict[str, Any] | None:
        if story is None:
            return None
        return {
            "id": story.id,
            "title": story.title,
            "short_answer": story.short_answer,
            "ninety_second_answer": story.ninety_second_answer,
            "detailed_answer": story.detailed_answer,
            "evidence_ids": story.evidence_ids,
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
            "source_excerpt": card.source_excerpt,
        }

    @staticmethod
    def _validate_feedback_output(output, payload: dict[str, Any], answer_text: str) -> None:
        grounding_raw = " ".join(_collect_text(payload) + [answer_text])
        PracticeService._validate_grounded_text(
            output.improved_answer,
            grounding_raw,
            label="Improved answer",
        )
        for strength in output.strengths:
            PracticeService._validate_grounded_text(strength, grounding_raw, label="Strength")
        for improvement in output.improvements:
            PracticeService._validate_grounded_text(improvement, grounding_raw, label="Improvement")
        PracticeService._validate_grounded_text(
            output.follow_up_question, grounding_raw, label="Follow-up question"
        )
        for unsupported_claim in output.unsupported_claims:
            PracticeService._validate_grounded_text(
                unsupported_claim.claim, answer_text, label="Unsupported claim"
            )
            PracticeService._validate_grounded_text(
                unsupported_claim.reason, grounding_raw, label="Unsupported claim reason"
            )
            if unsupported_claim.suggested_fix:
                PracticeService._validate_grounded_text(
                    unsupported_claim.suggested_fix,
                    grounding_raw,
                    label="Unsupported claim suggested fix",
                )

    @staticmethod
    def _validate_grounded_text(text: str, grounding_raw: str, *, label: str) -> None:
        grounding = _normalize(grounding_raw)
        for claim in NUMERIC_CLAIM_PATTERN.finditer(text):
            if _normalize(claim.group(0)) not in grounding:
                raise PracticeError(f"{label} contains an unsupported numeric claim.")
        for phrase in PROPER_NOUN_PHRASE_PATTERN.finditer(text):
            value = phrase.group(0).strip()
            if value in ALLOWED_CAPITALIZED_TERMS:
                continue
            if phrase.start() == 0 and len(value.split()) == 1:
                continue
            if _normalize(value) not in grounding:
                raise PracticeError(f"{label} contains an unsupported named claim.")
        grounding_terms = set(CONTENT_TOKEN_PATTERN.findall(grounding_raw.casefold()))
        for token in CONTENT_TOKEN_PATTERN.findall(text.casefold()):
            if token in ALLOWED_FEEDBACK_TERMS:
                continue
            if token not in grounding_terms:
                raise PracticeError(f"{label} contains an unsupported factual term.")

    @staticmethod
    def _comparison(*, output, previous: PracticeAttempt | None) -> dict[str, Any]:
        current_scores = {field: getattr(output, field) for field in SCORE_FIELDS}
        current_average = round(sum(current_scores.values()) / len(SCORE_FIELDS), 2)
        if previous is None:
            return {
                "previous_attempt_id": None,
                "component_deltas": {},
                "overall_delta": None,
                "current_average": current_average,
            }
        previous_scores = {field: getattr(previous, field) for field in SCORE_FIELDS}
        deltas = {field: current_scores[field] - previous_scores[field] for field in SCORE_FIELDS}
        previous_average = sum(previous_scores.values()) / len(SCORE_FIELDS)
        return {
            "previous_attempt_id": previous.id,
            "component_deltas": deltas,
            "overall_delta": round(current_average - previous_average, 2),
            "current_average": current_average,
        }

    @staticmethod
    def _require_owned_access(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
