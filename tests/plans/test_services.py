from datetime import timedelta

import pytest
from django.utils import timezone

from apps.plans.models import ImprovementPlan, ImprovementPlanStatus, PlanTaskStatus, PlanTaskType
from apps.plans.services import ImprovementPlanService
from apps.sprints.models import SprintState
from apps.sprints.services import SprintOwnershipError
from tests.plans.helpers import make_plan_ready_inputs

pytestmark = pytest.mark.django_db


def test_generate_plan_creates_tasks_and_marks_plan_ready():
    user, sprint, _, _ = make_plan_ready_inputs()
    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PLAN_READY
    assert plan.tasks.count() > 0
    assert plan.tasks.filter(task_type=PlanTaskType.PRACTICE).exists()
    assert plan.tasks.filter(
        day_number=plan.plan_length_days, task_type=PlanTaskType.FINAL_REVIEW
    ).exists()
    for day in range(1, plan.plan_length_days + 1):
        assert plan.tasks.filter(day_number=day).count() <= 2
        assert (
            sum(plan.tasks.filter(day_number=day).values_list("estimated_minutes", flat=True)) <= 45
        )


def test_generate_plan_is_idempotent_for_unchanged_inputs():
    user, sprint, _, _ = make_plan_ready_inputs("idempotent-plan@example.com")
    first = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    second = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    assert second.pk == first.pk
    assert (
        ImprovementPlan.objects.filter(sprint=sprint, status=ImprovementPlanStatus.ACTIVE).count()
        == 1
    )


def test_force_regeneration_preserves_completed_task_by_fingerprint():
    user, sprint, _, _ = make_plan_ready_inputs("preserve-plan@example.com")
    first = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    task = first.tasks.first()
    ImprovementPlanService.set_task_status(
        user=user,
        sprint=sprint,
        task_id=task.id,
        status=PlanTaskStatus.DONE,
    )
    second = ImprovementPlanService.generate_plan(user=user, sprint=sprint, force=True)
    first.refresh_from_db()
    preserved = second.tasks.get(task_fingerprint=task.task_fingerprint)
    assert first.status == ImprovementPlanStatus.STALE
    assert preserved.status == PlanTaskStatus.DONE
    assert preserved.completed_at is not None


def test_interview_date_compresses_plan():
    user, sprint, _, _ = make_plan_ready_inputs("compressed-plan@example.com")
    opportunity = sprint.opportunities.get()
    opportunity.interview_date = timezone.localdate() + timedelta(days=2)
    opportunity.save(update_fields=["interview_date", "updated_at"])
    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    assert plan.plan_length_days == 3
    assert plan.tasks.filter(day_number=3, task_type=PlanTaskType.FINAL_REVIEW).exists()


def test_complete_sprint_marks_completed():
    user, sprint, _, _ = make_plan_ready_inputs("complete-plan@example.com")
    ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    plan = ImprovementPlanService.complete_sprint(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert plan.status == ImprovementPlanStatus.COMPLETED
    assert sprint.state == SprintState.COMPLETED
    assert sprint.completed_at is not None


def test_cross_user_task_update_is_rejected(django_user_model):
    user, sprint, _, _ = make_plan_ready_inputs("owner-plan@example.com")
    other = django_user_model.objects.create_user(username="other-plan@example.com", password="pw")
    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    task = plan.tasks.first()
    with pytest.raises(SprintOwnershipError):
        ImprovementPlanService.set_task_status(
            user=other,
            sprint=sprint,
            task_id=task.id,
            status=PlanTaskStatus.DONE,
        )


def test_today_interview_plan_is_review_focused_and_within_daily_limits():
    user, sprint, _, _ = make_plan_ready_inputs("today-plan@example.com")
    opportunity = sprint.opportunities.get()
    opportunity.interview_date = timezone.localdate()
    opportunity.save(update_fields=["interview_date", "updated_at"])
    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    tasks = list(plan.tasks.filter(day_number=1))
    assert plan.plan_length_days == 1
    assert len(tasks) <= 2
    assert sum(task.estimated_minutes for task in tasks) <= 45
    assert tasks[0].task_type == PlanTaskType.FINAL_REVIEW


def test_rule_sources_create_traceable_tasks_and_goal_boosts_priority():
    user, sprint, _, _ = make_plan_ready_inputs("rule-sources-plan@example.com")
    opportunity = sprint.opportunities.get()
    opportunity.improvement_goals = "specificity"
    opportunity.save(update_fields=["improvement_goals", "updated_at"])
    evidence = sprint.active_profile.evidence_cards.filter(user=user).first()
    evidence.missing_details = ["specificity"]
    evidence.save(update_fields=["missing_details", "updated_at"])
    story = sprint.active_profile.stories.filter(user=user).first()
    story.specificity_score = 2
    story.save(update_fields=["specificity_score", "updated_at"])
    match = sprint.story_matches.first()
    match.missing_signal = "Needs specificity for the target role."
    match.save(update_fields=["missing_signal"])

    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    task_types = set(plan.tasks.values_list("task_type", flat=True))
    assert PlanTaskType.EVIDENCE_GAP in task_types
    assert PlanTaskType.STORY_IMPROVEMENT in task_types
    assert PlanTaskType.MATCH_GAP in task_types
    assert PlanTaskType.PRACTICE in task_types
    assert PlanTaskType.COMPANY_RESEARCH in task_types
    assert PlanTaskType.FINAL_REVIEW in task_types
    assert not any("confidence" in task.title.casefold() for task in plan.tasks.all())
    boosted = plan.tasks.get(task_type=PlanTaskType.STORY_IMPROVEMENT, linked_story=story)
    assert boosted.priority > 80
