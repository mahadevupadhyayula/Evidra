from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.matching.models import StoryMatch
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.plans.models import (
    ImprovementPlan,
    ImprovementPlanStatus,
    PlanTask,
    PlanTaskStatus,
    PlanTaskType,
)
from apps.practice.models import PracticeAttempt
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.models import Story, StoryStatus

WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z-]{3,}")
GENERIC_CONFIDENCE_PATTERN = re.compile(
    r"\b(be confident|confidence|believe in yourself)\b", re.IGNORECASE
)


class ImprovementPlanError(ValueError):
    """Raised when a seven-day improvement plan cannot be created safely."""


@dataclass(frozen=True)
class PlanCandidate:
    task_type: str
    title: str
    reason: str
    instructions: str
    estimated_minutes: int
    priority: int
    source_key: str
    linked_evidence_id: int | None = None
    linked_story_id: int | None = None
    linked_question_id: str = ""

    @property
    def fingerprint(self) -> str:
        raw = f"{self.task_type}:{self.source_key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class AssignedTask:
    candidate: PlanCandidate
    day_number: int
    daily_order: int


@dataclass(frozen=True)
class PlanContext:
    opportunity: Opportunity
    prepkit: PrepKit
    evidence: list[EvidenceCard]
    stories: list[Story]
    matches: list[StoryMatch]
    attempts: list[PracticeAttempt]


@dataclass(frozen=True)
class RuleBasedPlanEngine:
    @staticmethod
    def build_candidates(*, context: PlanContext) -> list[PlanCandidate]:
        candidates: list[PlanCandidate] = []
        goal_terms = _goal_terms(context.opportunity)
        candidates.extend(_evidence_gap_candidates(context.evidence, goal_terms))
        candidates.extend(_story_weakness_candidates(context.stories, context.matches, goal_terms))
        candidates.extend(_match_gap_candidates(context.matches, goal_terms))
        candidates.extend(_practice_weakness_candidates(context.attempts, goal_terms))
        candidates.extend(
            _company_research_candidates(context.opportunity, context.prepkit, goal_terms)
        )
        candidates.append(_final_review_candidate(context))
        candidates = [_apply_goal_boost(candidate, goal_terms) for candidate in candidates]
        candidates = [
            candidate
            for candidate in candidates
            if not GENERIC_CONFIDENCE_PATTERN.search(candidate.title)
        ]
        return _dedupe_candidates(candidates)

    @staticmethod
    def assign_days(
        *, candidates: list[PlanCandidate], plan_length_days: int
    ) -> list[AssignedTask]:
        final_tasks = [c for c in candidates if c.task_type == PlanTaskType.FINAL_REVIEW]
        work_tasks = [c for c in candidates if c.task_type != PlanTaskType.FINAL_REVIEW]
        work_tasks.sort(key=lambda item: (-item.priority, item.task_type, item.source_key))

        assignments: list[AssignedTask] = []
        minutes_by_day = {day: 0 for day in range(1, plan_length_days + 1)}
        count_by_day = {day: 0 for day in range(1, plan_length_days + 1)}
        work_days = list(range(1, plan_length_days))

        for candidate in work_tasks:
            for day in work_days:
                if count_by_day[day] >= 2:
                    continue
                if minutes_by_day[day] + candidate.estimated_minutes > 45:
                    continue
                assignments.append(
                    AssignedTask(
                        candidate=candidate, day_number=day, daily_order=count_by_day[day] + 1
                    )
                )
                minutes_by_day[day] += candidate.estimated_minutes
                count_by_day[day] += 1
                break

        final_candidate = final_tasks[0] if final_tasks else None
        if final_candidate:
            final_day = plan_length_days
            assignments.append(
                AssignedTask(
                    candidate=final_candidate,
                    day_number=final_day,
                    daily_order=count_by_day[final_day] + 1,
                )
            )
        assignments.sort(
            key=lambda item: (item.day_number, item.daily_order, -item.candidate.priority)
        )
        return assignments


@dataclass(frozen=True)
class ImprovementPlanService:
    @staticmethod
    def plan_context(*, user, sprint: InterviewSprint) -> dict[str, Any]:
        plan = None
        latest_plan = None
        access_error = ""
        try:
            ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
            plan = ImprovementPlanService.current_plan(user=user, sprint=sprint)
            latest_plan = ImprovementPlanService.latest_plan(user=user, sprint=sprint)
        except (
            InvalidSprintTransition,
            SprintOwnershipError,
            SprintTransitionConditionMissing,
            ImprovementPlanError,
        ) as exc:
            access_error = str(exc)
        return {
            "sprint": sprint,
            "plan": plan,
            "latest_plan": latest_plan,
            "tasks_by_day": ImprovementPlanService.tasks_by_day(user=user, plan=plan)
            if plan
            else [],
            "access_error": access_error,
        }

    @staticmethod
    def current_plan(*, user, sprint: InterviewSprint) -> ImprovementPlan | None:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        plan = (
            ImprovementPlan.objects.filter(
                sprint=sprint,
                sprint__user=user,
                status=ImprovementPlanStatus.ACTIVE,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if plan is None:
            return None
        try:
            current_revision = ImprovementPlanService.current_input_revision(
                user=user, sprint=sprint
            )
        except (
            InvalidSprintTransition,
            SprintOwnershipError,
            SprintTransitionConditionMissing,
            ImprovementPlanError,
        ):
            ImprovementPlanService.mark_stale_for_sprint(user=user, sprint=sprint)
            return None
        if plan.generated_from_revision != current_revision:
            ImprovementPlanService.mark_stale_for_sprint(
                user=user, sprint=sprint, exclude_revision=current_revision
            )
            return None
        return plan

    @staticmethod
    def latest_plan(*, user, sprint: InterviewSprint) -> ImprovementPlan | None:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        return (
            ImprovementPlan.objects.filter(sprint=sprint, sprint__user=user)
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def tasks_by_day(*, user, plan: ImprovementPlan) -> list[tuple[int, list[PlanTask]]]:
        if not user.is_authenticated or plan.sprint.user_id != user.id:
            raise SprintOwnershipError("Plan is not owned by this user.")
        tasks = list(
            PlanTask.objects.select_related("linked_evidence", "linked_story")
            .filter(plan=plan, plan__sprint__user=user)
            .order_by("day_number", "-priority", "id")
        )
        grouped: list[tuple[int, list[PlanTask]]] = []
        for day in range(1, plan.plan_length_days + 1):
            grouped.append((day, [task for task in tasks if task.day_number == day]))
        return grouped

    @staticmethod
    def generate_plan(*, user, sprint: InterviewSprint, force: bool = False) -> ImprovementPlan:
        ImprovementPlanService._require_generation_state(user=user, sprint=sprint)
        context = ImprovementPlanService._build_context(user=user, sprint=sprint)
        revision = ImprovementPlanService.build_input_revision(sprint=sprint, context=context)
        existing = ImprovementPlanService.current_plan(user=user, sprint=sprint)
        if existing and existing.generated_from_revision == revision and not force:
            return existing
        plan_length = ImprovementPlanService.plan_length_days(context.opportunity.interview_date)
        candidates = RuleBasedPlanEngine.build_candidates(context=context)
        assignments = RuleBasedPlanEngine.assign_days(
            candidates=candidates, plan_length_days=plan_length
        )
        if not assignments:
            raise ImprovementPlanError("Plan generation requires at least one source-backed task.")
        completed = ImprovementPlanService._completed_task_statuses(user=user, sprint=sprint)
        with transaction.atomic():
            ImprovementPlan.objects.select_for_update().filter(
                sprint=sprint,
                sprint__user=user,
                status__in=[ImprovementPlanStatus.DRAFT, ImprovementPlanStatus.ACTIVE],
            ).update(status=ImprovementPlanStatus.STALE, updated_at=timezone.now())
            plan = ImprovementPlan.objects.create(
                sprint=sprint,
                status=ImprovementPlanStatus.ACTIVE,
                interview_date=context.opportunity.interview_date,
                plan_length_days=plan_length,
                generated_from_revision=revision,
            )
            for assignment in assignments:
                candidate = assignment.candidate
                prior_status, prior_completed_at = completed.get(
                    candidate.fingerprint,
                    (PlanTaskStatus.TODO, None),
                )
                PlanTask.objects.create(
                    plan=plan,
                    day_number=assignment.day_number,
                    task_type=candidate.task_type,
                    title=candidate.title,
                    reason=candidate.reason,
                    instructions=candidate.instructions,
                    estimated_minutes=candidate.estimated_minutes,
                    linked_evidence_id=candidate.linked_evidence_id,
                    linked_story_id=candidate.linked_story_id,
                    linked_question_id=candidate.linked_question_id,
                    priority=candidate.priority,
                    status=prior_status,
                    completed_at=prior_completed_at,
                    task_fingerprint=candidate.fingerprint,
                )
            SprintWorkflowService.mark_plan_ready(user=user, sprint=sprint, plan=plan)
            return plan

    @staticmethod
    def set_task_status(*, user, sprint: InterviewSprint, task_id: int, status: str) -> PlanTask:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        target_status = PlanTaskStatus(status)
        with transaction.atomic():
            try:
                task = (
                    PlanTask.objects.select_for_update()
                    .select_related("plan", "plan__sprint")
                    .get(
                        pk=task_id,
                        plan__sprint=sprint,
                        plan__sprint__user=user,
                        plan__status=ImprovementPlanStatus.ACTIVE,
                    )
                )
            except PlanTask.DoesNotExist as exc:
                raise SprintOwnershipError("Plan task is not owned by this user.") from exc
            task.status = target_status
            task.completed_at = timezone.now() if target_status == PlanTaskStatus.DONE else None
            task.save(update_fields=["status", "completed_at"])
            return task

    @staticmethod
    def complete_sprint(*, user, sprint: InterviewSprint) -> ImprovementPlan:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        plan = ImprovementPlanService.current_plan(user=user, sprint=sprint)
        if plan is None:
            raise SprintTransitionConditionMissing(
                "A current active plan is required before completion."
            )
        with transaction.atomic():
            locked_plan = ImprovementPlan.objects.select_for_update().get(
                pk=plan.pk, sprint=sprint, sprint__user=user
            )
            locked_plan.status = ImprovementPlanStatus.COMPLETED
            locked_plan.save(update_fields=["status", "updated_at"])
            SprintWorkflowService.mark_completed(user=user, sprint=sprint, plan=locked_plan)
            return locked_plan

    @staticmethod
    def mark_stale_for_sprint(
        *, user, sprint: InterviewSprint, exclude_revision: str | None = None
    ) -> int:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        queryset = ImprovementPlan.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status__in=[ImprovementPlanStatus.DRAFT, ImprovementPlanStatus.ACTIVE],
        )
        if exclude_revision:
            queryset = queryset.exclude(generated_from_revision=exclude_revision)
        return queryset.update(status=ImprovementPlanStatus.STALE, updated_at=timezone.now())

    @staticmethod
    def current_input_revision(*, user, sprint: InterviewSprint) -> str:
        context = ImprovementPlanService._build_context(user=user, sprint=sprint)
        return ImprovementPlanService.build_input_revision(sprint=sprint, context=context)

    @staticmethod
    def build_input_revision(*, sprint: InterviewSprint, context: PlanContext) -> str:
        payload = {
            "sprint": sprint.id,
            "profile": sprint.active_profile_id,
            "opportunity": {
                "id": context.opportunity.id,
                "updated_at": context.opportunity.updated_at.isoformat(),
                "interview_date": context.opportunity.interview_date.isoformat()
                if context.opportunity.interview_date
                else None,
                "goals": context.opportunity.improvement_goals,
                "concerns": context.opportunity.concerns,
            },
            "prepkit": {
                "id": context.prepkit.id,
                "input_revision": context.prepkit.input_revision,
                "updated_at": context.prepkit.updated_at.isoformat(),
            },
            "evidence": [
                (item.id, item.updated_at.isoformat(), item.status) for item in context.evidence
            ],
            "stories": [
                (
                    item.id,
                    item.updated_at.isoformat(),
                    item.status,
                    item.quality_score,
                    item.specificity_score,
                    item.impact_score,
                    item.ownership_score,
                    item.clarity_score,
                )
                for item in context.stories
            ],
            "matches": [
                (item.id, item.created_at.isoformat(), item.total_score, item.user_selected)
                for item in context.matches
            ],
            "attempts": [
                (
                    item.id,
                    item.created_at.isoformat(),
                    item.question_id,
                    item.relevance_score,
                    item.structure_score,
                    item.specificity_score,
                    item.ownership_score,
                    item.impact_score,
                    item.clarity_score,
                )
                for item in context.attempts
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:40]

    @staticmethod
    def plan_length_days(interview_date: date | None) -> int:
        if interview_date is None:
            return 7
        days_until = (interview_date - timezone.localdate()).days + 1
        if days_until <= 0:
            return 7
        return min(7, max(1, days_until))

    @staticmethod
    def _build_context(*, user, sprint: InterviewSprint) -> PlanContext:
        ImprovementPlanService._require_generation_state(user=user, sprint=sprint)
        opportunity = (
            Opportunity.objects.filter(
                sprint=sprint,
                sprint__user=user,
                confirmation_status=OpportunityStatus.CONFIRMED,
            )
            .order_by("-confirmed_at", "-updated_at", "-id")
            .first()
        )
        if opportunity is None:
            raise SprintTransitionConditionMissing(
                "A confirmed opportunity is required before planning."
            )
        prepkit = (
            PrepKit.objects.filter(
                sprint=sprint,
                sprint__user=user,
                status=PrepKitStatus.READY,
            )
            .order_by("-generated_at", "-created_at", "-id")
            .first()
        )
        if prepkit is None:
            raise SprintTransitionConditionMissing("A ready Prep Kit is required before planning.")
        evidence = list(
            EvidenceCard.objects.filter(
                user=user, profile=sprint.active_profile, status=EvidenceStatus.APPROVED
            ).order_by("-updated_at", "-id")
        )
        stories = list(
            Story.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status__in=[StoryStatus.READY, StoryStatus.EDITED],
            ).order_by("-updated_at", "-id")
        )
        matches = list(
            StoryMatch.objects.filter(sprint=sprint, sprint__user=user).order_by(
                "competency_key", "-total_score", "-created_at"
            )
        )
        attempts = list(
            PracticeAttempt.objects.filter(sprint=sprint, sprint__user=user).order_by(
                "question_id", "-attempt_number", "-created_at"
            )
        )
        if not attempts:
            raise SprintTransitionConditionMissing(
                "At least one practice attempt is required before planning."
            )
        return PlanContext(
            opportunity=opportunity,
            prepkit=prepkit,
            evidence=evidence,
            stories=stories,
            matches=matches,
            attempts=attempts,
        )

    @staticmethod
    def _require_generation_state(*, user, sprint: InterviewSprint) -> None:
        ImprovementPlanService._require_owned_access(user=user, sprint=sprint)
        if SprintState(sprint.state) not in {SprintState.PRACTICE_ACTIVE, SprintState.PLAN_READY}:
            raise InvalidSprintTransition(
                f"Cannot create a plan while Sprint is in {sprint.state}."
            )

    @staticmethod
    def _require_owned_access(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")

    @staticmethod
    def _completed_task_statuses(*, user, sprint: InterviewSprint) -> dict[str, tuple[str, Any]]:
        prior_tasks = PlanTask.objects.filter(
            plan__sprint=sprint,
            plan__sprint__user=user,
            status__in=[PlanTaskStatus.DONE, PlanTaskStatus.SKIPPED],
        ).order_by("-created_at")
        preserved: dict[str, tuple[str, Any]] = {}
        for task in prior_tasks:
            preserved.setdefault(task.task_fingerprint, (task.status, task.completed_at))
        return preserved


def _goal_terms(opportunity: Opportunity) -> set[str]:
    return {
        term.casefold()
        for term in WORD_PATTERN.findall(f"{opportunity.improvement_goals} {opportunity.concerns}")
    }


def _text_terms(*values: object) -> set[str]:
    return {term.casefold() for value in values for term in WORD_PATTERN.findall(str(value or ""))}


def _apply_goal_boost(candidate: PlanCandidate, goal_terms: set[str]) -> PlanCandidate:
    if not goal_terms:
        return candidate
    if _text_terms(candidate.title, candidate.reason, candidate.instructions) & goal_terms:
        return PlanCandidate(
            **{**candidate.__dict__, "priority": min(100, candidate.priority + 10)}
        )
    return candidate


def _evidence_gap_candidates(
    evidence: list[EvidenceCard], goal_terms: set[str]
) -> list[PlanCandidate]:
    candidates = []
    for card in evidence:
        missing = [str(item) for item in (card.missing_details or []) if str(item).strip()]
        if missing:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.EVIDENCE_GAP,
                    title=f"Strengthen evidence: {card.title}",
                    reason=f"This approved evidence is missing: {missing[0]}",
                    instructions=(
                        "Add truthful details supported by your experience or source material."
                    ),
                    estimated_minutes=20,
                    priority=75,
                    source_key=f"evidence:{card.id}:missing:{missing[0]}",
                    linked_evidence_id=card.id,
                )
            )
        if not (card.result or "").strip():
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.EVIDENCE_GAP,
                    title=f"Clarify result for evidence: {card.title}",
                    reason="This approved evidence needs a clearer result.",
                    instructions=("Write the result plainly. Add metrics only when sourced."),
                    estimated_minutes=20,
                    priority=73,
                    source_key=f"evidence:{card.id}:result",
                    linked_evidence_id=card.id,
                )
            )
    return candidates


def _story_weakness_candidates(
    stories: list[Story], matches: list[StoryMatch], goal_terms: set[str]
) -> list[PlanCandidate]:
    selected_ids = {
        m.selected_story_id or m.primary_story_id
        for m in matches
        if m.selected_story_id or m.primary_story_id
    }
    candidates = []
    for story in stories:
        score_checks = [
            (
                story.specificity_score,
                "specificity",
                "Add concrete context from approved evidence.",
            ),
            (story.impact_score, "impact", "Make the result and learning easier to explain."),
            (story.ownership_score, "ownership", "Clarify what you personally owned and decided."),
            (
                story.clarity_score,
                "clarity",
                "Tighten the answer structure for a concise interview response.",
            ),
            (
                story.quality_score,
                "overall quality",
                "Polish the story before using it in priority practice.",
            ),
        ]
        for score, label, instruction in score_checks:
            if score is not None and score <= 3:
                candidates.append(
                    PlanCandidate(
                        task_type=PlanTaskType.STORY_IMPROVEMENT,
                        title=f"Improve {label}: {story.title}",
                        reason=f"The story has a low {label} score.",
                        instructions=instruction,
                        estimated_minutes=25,
                        priority=88 if story.id in selected_ids else 80,
                        source_key=f"story:{story.id}:score:{label}",
                        linked_story_id=story.id,
                    )
                )
        missing = [str(item) for item in (story.missing_details or []) if str(item).strip()]
        if missing:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.STORY_IMPROVEMENT,
                    title=f"Fill story detail: {story.title}",
                    reason=f"The story is missing: {missing[0]}",
                    instructions=("Update the story with supported detail from approved evidence."),
                    estimated_minutes=25,
                    priority=82,
                    source_key=f"story:{story.id}:missing:{missing[0]}",
                    linked_story_id=story.id,
                )
            )
    return candidates


def _match_gap_candidates(matches: list[StoryMatch], goal_terms: set[str]) -> list[PlanCandidate]:
    candidates = []
    for match in matches:
        story_id = match.selected_story_id or match.primary_story_id
        if match.missing_signal:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.MATCH_GAP,
                    title=f"Address match gap: {match.competency_label or match.competency_key}",
                    reason=match.missing_signal,
                    instructions=match.recommended_emphasis
                    or "Prepare a concise explanation for this role gap using approved evidence.",
                    estimated_minutes=25,
                    priority=88,
                    source_key=f"match:{match.id}:missing",
                    linked_story_id=story_id,
                )
            )
        elif match.total_score <= 60:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.MATCH_GAP,
                    title=f"Sharpen role fit: {match.competency_label or match.competency_key}",
                    reason="This competency has a lower match score than the story map.",
                    instructions=match.recommended_emphasis
                    or "Review the best story and add one supported role-relevant detail.",
                    estimated_minutes=25,
                    priority=85,
                    source_key=f"match:{match.id}:score",
                    linked_story_id=story_id,
                )
            )
    return candidates


def _practice_weakness_candidates(
    attempts: list[PracticeAttempt], goal_terms: set[str]
) -> list[PlanCandidate]:
    latest_by_question: dict[str, PracticeAttempt] = {}
    for attempt in attempts:
        latest_by_question.setdefault(attempt.question_id, attempt)
    candidates = []
    for attempt in latest_by_question.values():
        scores = {
            "relevance": attempt.relevance_score,
            "structure": attempt.structure_score,
            "specificity": attempt.specificity_score,
            "ownership": attempt.ownership_score,
            "impact": attempt.impact_score,
            "clarity": attempt.clarity_score,
        }
        weakest = min(scores.items(), key=lambda item: item[1])
        if weakest[1] <= 3:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.PRACTICE,
                    title=f"Re-practice question {attempt.question_id}",
                    reason=f"Your latest answer needs work on {weakest[0]}.",
                    instructions=(
                        "Rewrite the answer using the improved answer, then submit again."
                    ),
                    estimated_minutes=30,
                    priority=95,
                    source_key=f"practice:{attempt.question_id}:score:{attempt.id}:{weakest[0]}",
                    linked_story_id=attempt.linked_story_id,
                    linked_question_id=attempt.question_id,
                )
            )
        unsupported = (
            attempt.feedback.get("unsupported_claims") if isinstance(attempt.feedback, dict) else []
        )
        if unsupported:
            candidates.append(
                PlanCandidate(
                    task_type=PlanTaskType.PRACTICE,
                    title=f"Ground unsupported claims in {attempt.question_id}",
                    reason="Your practice feedback flagged unsupported claims.",
                    instructions="Remove unsupported claims or tie them to approved evidence.",
                    estimated_minutes=20,
                    priority=92,
                    source_key=f"practice:{attempt.question_id}:unsupported:{attempt.id}",
                    linked_story_id=attempt.linked_story_id,
                    linked_question_id=attempt.question_id,
                )
            )
    return candidates


def _company_research_candidates(
    opportunity: Opportunity, prepkit: PrepKit, goal_terms: set[str]
) -> list[PlanCandidate]:
    if not opportunity.company_name and not opportunity.company_context:
        return []
    return [
        PlanCandidate(
            task_type=PlanTaskType.COMPANY_RESEARCH,
            title=f"Prepare company talking points for {opportunity.company_name or 'the company'}",
            reason="A bounded company review connects approved stories to this opportunity.",
            instructions=(
                "Review confirmed company context and Prep Kit notes. "
                "Write three talking points; do not perform broad web research."
            ),
            estimated_minutes=25,
            priority=60,
            source_key=f"company:{opportunity.id}",
        )
    ]


def _final_review_candidate(context: PlanContext) -> PlanCandidate:
    return PlanCandidate(
        task_type=PlanTaskType.FINAL_REVIEW,
        title="Final interview review",
        reason="The final day should focus on review, not new material.",
        instructions=(
            "Review top matched stories, practice priorities, talking points, and checklist."
        ),
        estimated_minutes=30,
        priority=100,
        source_key=f"final:{context.opportunity.id}:{context.prepkit.id}",
    )


def _dedupe_candidates(candidates: list[PlanCandidate]) -> list[PlanCandidate]:
    seen = set()
    deduped = []
    for candidate in candidates:
        if candidate.fingerprint in seen:
            continue
        seen.add(candidate.fingerprint)
        deduped.append(candidate)
    return deduped
