from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AIProfileExtractionError
from apps.profiles.forms import CareerProfileForm
from apps.profiles.services import CareerProfileError, CareerProfileService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


@login_required
def profile_review(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    if sprint.state == SprintState.DRAFT:
        messages.error(request, "Confirm your resume before creating your profile.")
        return redirect("documents:resume_upload")
    try:
        if sprint.state == SprintState.RESUME_READY:
            profile = CareerProfileService.get_or_create_draft_profile(
                user=request.user, sprint=sprint
            )
        else:
            profile = CareerProfileService.get_current_profile(request.user, sprint)
            if profile is None:
                raise SprintTransitionConditionMissing("A confirmed active profile is required.")
    except (
        AIProfileExtractionError,
        CareerProfileError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    form = CareerProfileForm(instance=profile)
    return render(
        request,
        "profiles/review.html",
        {"form": form, "profile": profile, "sprint": sprint},
    )


@login_required
@require_POST
def profile_generate(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        CareerProfileService.ensure_draft_profile(user=request.user, sprint=sprint)
    except (
        AIProfileExtractionError,
        CareerProfileError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Profile draft generated from your confirmed resume.")
    return redirect("profiles:profile_review")


@login_required
@require_POST
def profile_save(request, profile_id):
    profile = CareerProfileService.get_owned_profile(request.user, profile_id)
    form = CareerProfileForm(request.POST, instance=profile)
    if form.is_valid():
        try:
            profile = CareerProfileService.update_profile(
                user=request.user,
                profile_id=profile.pk,
                cleaned_data=form.cleaned_data,
            )
        except CareerProfileError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Profile draft saved.")
        return redirect("profiles:profile_review")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    return render(
        request,
        "profiles/review.html",
        {"form": form, "profile": profile, "sprint": sprint},
    )


@login_required
@require_POST
def profile_confirm(request, profile_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    profile = CareerProfileService.get_owned_profile(request.user, profile_id)
    form = CareerProfileForm(request.POST, instance=profile)
    if form.is_valid():
        try:
            CareerProfileService.confirm_profile(
                user=request.user,
                sprint=sprint,
                profile_id=profile.pk,
                cleaned_data=form.cleaned_data,
            )
        except (
            CareerProfileError,
            InvalidSprintTransition,
            SprintTransitionConditionMissing,
        ) as exc:
            messages.error(request, str(exc))
            return redirect("profiles:profile_review")
        messages.success(
            request,
            "Profile confirmed. Your Sprint is ready for opportunity context next.",
        )
        return redirect("workspace:index")
    return render(
        request,
        "profiles/review.html",
        {"form": form, "profile": profile, "sprint": sprint},
    )
