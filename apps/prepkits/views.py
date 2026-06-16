from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.generations.services import GenerationRunService
from apps.prepkits.forms import PrepKitGenerateForm, PrepKitRetryForm
from apps.prepkits.services import PrepKitError, PrepKitService
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def _context(user, sprint):
    prepkit = None
    latest_prepkit = None
    available_prepkit = None
    run = None
    error = None
    try:
        PrepKitService.require_paid_access(user=user, sprint=sprint)
        current_prepkit = PrepKitService.current_prepkit(user=user, sprint=sprint)
        latest_prepkit = PrepKitService.latest_prepkit(user=user, sprint=sprint)
        available_prepkit = PrepKitService.latest_available_prepkit(user=user, sprint=sprint)
        prepkit = current_prepkit or available_prepkit
        run = GenerationRunService.current_prepkit_run(user=user, sprint=sprint)
    except (InvalidSprintTransition, SprintOwnershipError, SprintTransitionConditionMissing) as exc:
        error = str(exc)
    return {
        "sprint": sprint,
        "prepkit": prepkit,
        "latest_prepkit": latest_prepkit,
        "available_prepkit": available_prepkit,
        "generation_run": run,
        "generate_form": PrepKitGenerateForm(),
        "retry_form": PrepKitRetryForm(),
        "access_error": error,
    }


@login_required
def prepkit_detail(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    return render(request, "prepkits/detail.html", _context(request.user, sprint))


@login_required
@require_POST
def prepkit_generate(request):
    form = PrepKitGenerateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not start Prep Kit generation. Please reload and try again.")
        return redirect("prepkits:detail")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        GenerationRunService.enqueue_prepkit(user=request.user, sprint=sprint)
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        PrepKitError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Prep Kit generation has been queued.")
    return redirect("prepkits:detail")


@login_required
def prepkit_status(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    return render(request, "prepkits/_generation_status.html", _context(request.user, sprint))


@login_required
@require_POST
def prepkit_retry(request):
    form = PrepKitRetryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not retry Prep Kit generation. Please reload and try again.")
        return redirect("prepkits:detail")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        GenerationRunService.enqueue_prepkit(user=request.user, sprint=sprint, force=True)
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        PrepKitError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Prep Kit generation retry has been queued.")
    return redirect("prepkits:detail")


@login_required
def prepkit_print(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    prepkit = PrepKitService.current_prepkit(user=request.user, sprint=sprint)
    if prepkit is None:
        prepkit = PrepKitService.latest_available_prepkit(user=request.user, sprint=sprint)
    if prepkit is None:
        messages.error(request, "A ready Prep Kit is required before printing.")
        return redirect("prepkits:detail")
    return render(request, "prepkits/print.html", {"sprint": sprint, "prepkit": prepkit})
