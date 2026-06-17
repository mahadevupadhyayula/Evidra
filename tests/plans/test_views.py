import pytest

from apps.plans.models import PlanTaskStatus
from apps.sprints.models import SprintState
from tests.plans.helpers import make_plan_ready_inputs

pytestmark = pytest.mark.django_db


def test_plan_generate_view_creates_plan(client):
    user, sprint, _, _ = make_plan_ready_inputs("view-plan@example.com")
    client.force_login(user)
    response = client.post("/workspace/plan/generate/", follow=True)
    sprint.refresh_from_db()
    assert response.status_code == 200
    assert sprint.state == SprintState.PLAN_READY
    assert sprint.improvement_plans.get().tasks.exists()


def test_task_status_view_filters_to_current_user(client, django_user_model):
    user, sprint, _, _ = make_plan_ready_inputs("task-view-owner@example.com")
    client.force_login(user)
    client.post("/workspace/plan/generate/")
    task = sprint.improvement_plans.get().tasks.first()
    other = django_user_model.objects.create_user(
        username="task-view-other@example.com", password="pw"
    )
    client.force_login(other)
    response = client.post(
        f"/workspace/plan/tasks/{task.id}/status/",
        {"status": PlanTaskStatus.DONE},
        follow=True,
    )
    task.refresh_from_db()
    assert response.status_code == 200
    assert task.status == PlanTaskStatus.TODO


def test_complete_view_marks_sprint_completed(client):
    user, sprint, _, _ = make_plan_ready_inputs("complete-view@example.com")
    client.force_login(user)
    client.post("/workspace/plan/generate/")
    response = client.post("/workspace/plan/complete/", {"confirm": "on"}, follow=True)
    sprint.refresh_from_db()
    assert response.status_code == 200
    assert sprint.state == SprintState.COMPLETED


def test_complete_view_requires_confirmation(client):
    user, sprint, _, _ = make_plan_ready_inputs("confirm-complete-view@example.com")
    client.force_login(user)
    client.post("/workspace/plan/generate/")
    response = client.post("/workspace/plan/complete/", follow=True)
    sprint.refresh_from_db()
    assert response.status_code == 200
    assert sprint.state == SprintState.PLAN_READY
