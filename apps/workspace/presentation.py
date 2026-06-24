from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from apps.sprints.models import SprintState


@dataclass(frozen=True)
class WorkflowStepDefinition:
    number: int
    label: str
    state: str
    url_name: str | None = None


WORKFLOW_STEP_DEFINITIONS = (
    WorkflowStepDefinition(1, "Resume", "resume", "documents:resume_upload"),
    WorkflowStepDefinition(2, "Profile", "profile", "profiles:profile_review"),
    WorkflowStepDefinition(3, "Opportunity", "opportunity", "opportunities:opportunity_detail"),
    WorkflowStepDefinition(4, "Evidence", "evidence", "evidence:evidence_review"),
    WorkflowStepDefinition(5, "Stories", "stories", "stories:story_bank"),
    WorkflowStepDefinition(6, "Matching", "matching", "matching:index"),
    WorkflowStepDefinition(7, "Preview", "preview", "previews:detail"),
    WorkflowStepDefinition(8, "Prep Kit", "prepkit", "prepkits:detail"),
    WorkflowStepDefinition(9, "Practice", "practice", "practice:index"),
    WorkflowStepDefinition(10, "Plan", "plan", "plans:detail"),
)

SPRINT_STATE_TO_WORKFLOW_STEP = {
    SprintState.DRAFT: 1,
    SprintState.RESUME_READY: 2,
    SprintState.PROFILE_CONFIRMED: 3,
    SprintState.OPPORTUNITY_CONFIRMED: 4,
    SprintState.EVIDENCE_REVIEW: 4,
    SprintState.EVIDENCE_APPROVED: 5,
    SprintState.STORIES_READY: 6,
    SprintState.MATCHING_READY: 7,
    SprintState.PREVIEW_READY: 8,
    SprintState.PAYMENT_PENDING: 8,
    SprintState.PAID: 8,
    SprintState.PREPKIT_READY: 9,
    SprintState.PRACTICE_ACTIVE: 9,
    SprintState.PLAN_READY: 10,
    SprintState.COMPLETED: 10,
}


def build_workflow_steps(
    sprint_state: SprintState | str | None,
    *,
    url_resolver: Callable[[str], str] | None = None,
) -> list[dict[str, object]]:
    """Project deterministic Sprint states onto presentation-only workspace steps."""

    current_step_number = SPRINT_STATE_TO_WORKFLOW_STEP.get(sprint_state)
    steps = []

    for step in WORKFLOW_STEP_DEFINITIONS:
        if current_step_number is None:
            status = "locked"
        elif step.number < current_step_number:
            status = "complete"
        elif step.number == current_step_number:
            status = "current"
        else:
            status = "locked"

        target_url = None
        if url_resolver is not None and step.url_name is not None and status != "locked":
            target_url = url_resolver(step.url_name)

        steps.append(
            {
                "label": step.label,
                "number": step.number,
                "status": status,
                "target_url": target_url,
            }
        )

    return steps
