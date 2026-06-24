from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.sprints.services import SprintWorkflowService
from apps.workspace.presentation import build_workflow_steps


@login_required
def index(request):
    sprint = (
        request.user.interview_sprints.exclude(state="COMPLETED")
        .order_by("-created_at", "-id")
        .first()
    )
    workflow_steps = build_workflow_steps(
        sprint.state if sprint else None,
        url_resolver=reverse,
    )
    return render(
        request,
        "workspace/index.html",
        {"sprint": sprint, "workflow_steps": workflow_steps},
    )


@login_required
@require_POST
def current_sprint(request):
    SprintWorkflowService.get_or_create_current_sprint(request.user)
    return redirect("workspace:index")
