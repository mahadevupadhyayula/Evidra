from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AIPreviewGenerationError
from apps.previews.services import ReadinessPreviewError, ReadinessPreviewService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def _redirect_before_preview_stage(sprint):
    if sprint.state in {
        SprintState.DRAFT,
        SprintState.RESUME_READY,
        SprintState.PROFILE_CONFIRMED,
        SprintState.OPPORTUNITY_CONFIRMED,
        SprintState.EVIDENCE_REVIEW,
        SprintState.EVIDENCE_APPROVED,
        SprintState.STORIES_READY,
    }:
        return "matching:index"
    return None


@login_required
def preview_detail(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    redirect_target = _redirect_before_preview_stage(sprint)
    if redirect_target:
        messages.error(request, "Generate contextual matches before the readiness preview.")
        return redirect(redirect_target)
    try:
        preview = ReadinessPreviewService.current_preview(user=request.user, sprint=sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    return render(request, "previews/detail.html", {"sprint": sprint, "preview": preview})


@login_required
@require_POST
def preview_generate(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    force = request.POST.get("force") == "1"
    try:
        ReadinessPreviewService.generate_preview(user=request.user, sprint=sprint, force=force)
    except (
        AIPreviewGenerationError,
        ReadinessPreviewError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Generated your free readiness preview.")
    return redirect("previews:detail")
