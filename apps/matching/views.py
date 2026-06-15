from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AIStoryMatchScoringError
from apps.matching.forms import StoryMatchOverrideForm
from apps.matching.services import MatchingError, MatchingService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def _redirect_before_matching_stage(sprint):
    if sprint.state in {
        SprintState.DRAFT,
        SprintState.RESUME_READY,
        SprintState.PROFILE_CONFIRMED,
        SprintState.OPPORTUNITY_CONFIRMED,
        SprintState.EVIDENCE_REVIEW,
        SprintState.EVIDENCE_APPROVED,
    }:
        return "stories:story_bank"
    return None


@login_required
def matching_index(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    redirect_target = _redirect_before_matching_stage(sprint)
    if redirect_target:
        messages.error(request, "Generate reusable stories before contextual matching.")
        return redirect(redirect_target)
    try:
        matches = MatchingService.list_matches(user=request.user, sprint=sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    return render(request, "matching/index.html", {"sprint": sprint, "matches": matches})


@login_required
@require_POST
def matching_generate(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    force = request.POST.get("force") == "1"
    try:
        matches = MatchingService.generate_matches(user=request.user, sprint=sprint, force=force)
    except (
        AIStoryMatchScoringError,
        MatchingError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Generated {len(matches)} contextual match(es).")
    return redirect("matching:index")


@login_required
@require_POST
def matching_override(request, match_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    form = StoryMatchOverrideForm(request.POST)
    if form.is_valid():
        try:
            MatchingService.set_user_override(
                user=request.user,
                sprint=sprint,
                match_id=match_id,
                story_id=form.cleaned_data.get("selected_story_id"),
            )
        except (MatchingError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Story override saved.")
    else:
        messages.error(request, "Choose a valid story override.")
    return redirect("matching:index")
