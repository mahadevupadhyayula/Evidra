from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.plans.forms import PlanGenerateForm, PlanTaskStatusForm, SprintCompleteForm
from apps.plans.services import ImprovementPlanError, ImprovementPlanService
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


@login_required
def plan_detail(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    context = ImprovementPlanService.plan_context(user=request.user, sprint=sprint)
    context["generate_form"] = PlanGenerateForm()
    context["complete_form"] = SprintCompleteForm()
    return render(request, "plans/detail.html", context)


@login_required
@require_POST
def plan_generate(request):
    form = PlanGenerateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not generate your plan. Please reload and try again.")
        return redirect("plans:detail")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        ImprovementPlanService.generate_plan(
            user=request.user,
            sprint=sprint,
            force=form.cleaned_data.get("force", False),
        )
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        ImprovementPlanError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Your seven-day plan is ready.")
    return redirect("plans:detail")


@login_required
@require_POST
def task_status(request, task_id):
    form = PlanTaskStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid task status.")
        return redirect("plans:detail")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        ImprovementPlanService.set_task_status(
            user=request.user,
            sprint=sprint,
            task_id=task_id,
            status=form.cleaned_data["status"],
        )
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        ImprovementPlanError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Task updated.")
    return redirect("plans:detail")


@login_required
@require_POST
def plan_complete(request):
    form = SprintCompleteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not complete the Sprint. Please reload and try again.")
        return redirect("plans:detail")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        ImprovementPlanService.complete_sprint(user=request.user, sprint=sprint)
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        ImprovementPlanError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Interview Sprint completed.")
    return redirect("workspace:index")
