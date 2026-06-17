import pytest
from django.db import IntegrityError

from apps.plans.models import (
    ImprovementPlan,
    ImprovementPlanStatus,
    PlanTask,
    PlanTaskStatus,
    PlanTaskType,
)
from tests.plans.helpers import make_plan_ready_inputs

pytestmark = pytest.mark.django_db


def test_plan_and_task_defaults():
    user, sprint, _, _ = make_plan_ready_inputs()
    plan = ImprovementPlan.objects.create(sprint=sprint, generated_from_revision="rev")
    task = PlanTask.objects.create(
        plan=plan,
        day_number=1,
        task_type=PlanTaskType.FINAL_REVIEW,
        title="Final review",
        reason="Review current materials.",
        instructions="Review approved stories.",
        estimated_minutes=30,
        priority=1,
        task_fingerprint="final",
    )
    assert user.is_authenticated
    assert plan.status == ImprovementPlanStatus.ACTIVE
    assert plan.plan_length_days == 7
    assert task.status == PlanTaskStatus.TODO


def test_only_one_current_plan_per_sprint():
    _, sprint, _, _ = make_plan_ready_inputs("unique-plan@example.com")
    ImprovementPlan.objects.create(sprint=sprint, generated_from_revision="rev1")
    with pytest.raises(IntegrityError):
        ImprovementPlan.objects.create(sprint=sprint, generated_from_revision="rev2")
