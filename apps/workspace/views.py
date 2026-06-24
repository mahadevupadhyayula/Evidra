from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.opportunities.services import OpportunityService
from apps.sprints.services import SprintWorkflowService
from apps.workspace.presentation import (
    build_current_opportunity_summary,
    build_next_step,
    build_workflow_steps,
)


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
    current_opportunity = (
        OpportunityService.get_current_opportunity(user=request.user, sprint=sprint)
        if sprint is not None
        else None
    )
    opportunity_summary = build_current_opportunity_summary(current_opportunity, workflow_steps)
    next_step = build_next_step(request.user, sprint, url_resolver=reverse)
    return render(
        request,
        "workspace/index.html",
        {
            "sprint": sprint,
            "workflow_steps": workflow_steps,
            "next_step": next_step,
            "opportunity_summary": opportunity_summary,
        },
    )


@login_required
@require_POST
def current_sprint(request):
    SprintWorkflowService.get_or_create_current_sprint(request.user)
    return redirect("workspace:index")
