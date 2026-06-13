from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.sprints.services import SprintWorkflowService


@login_required
def index(request):
    sprint = (
        request.user.interview_sprints.exclude(state="COMPLETED")
        .order_by("-created_at", "-id")
        .first()
    )
    return render(request, "workspace/index.html", {"sprint": sprint})


@login_required
@require_POST
def current_sprint(request):
    SprintWorkflowService.get_or_create_current_sprint(request.user)
    return redirect("workspace:index")
