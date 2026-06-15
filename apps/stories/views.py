from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AIStoryGenerationError, AIStoryScoringError
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from apps.stories.forms import StoryEditForm
from apps.stories.services import StoryError, StoryService


def _redirect_before_story_stage(sprint):
    if sprint.state in {SprintState.DRAFT, SprintState.RESUME_READY}:
        return "workspace:index"
    if sprint.state == SprintState.PROFILE_CONFIRMED:
        return "opportunities:opportunity_detail"
    if sprint.state in {SprintState.OPPORTUNITY_CONFIRMED, SprintState.EVIDENCE_REVIEW}:
        return "evidence:evidence_review"
    return None


@login_required
def story_bank(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    redirect_target = _redirect_before_story_stage(sprint)
    if redirect_target:
        messages.error(request, "Approve evidence before generating reusable stories.")
        return redirect(redirect_target)
    try:
        stories = StoryService.list_stories(user=request.user, sprint=sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    return render(request, "stories/index.html", {"sprint": sprint, "stories": stories})


@login_required
@require_POST
def story_generate(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        created = StoryService.generate_stories(user=request.user, sprint=sprint)
    except (
        AIStoryGenerationError,
        AIStoryScoringError,
        StoryError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        if created:
            messages.success(request, f"Generated {len(created)} reusable storie(s).")
        else:
            messages.success(request, "Reusable stories are already ready.")
    return redirect("stories:story_bank")


@login_required
def story_edit(request, story_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        story = StoryService.get_owned_story(user=request.user, sprint=sprint, story_id=story_id)
        choices = StoryService.approved_evidence_choices(user=request.user, sprint=sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    if request.method == "POST":
        form = StoryEditForm(request.POST, instance=story, approved_evidence_choices=choices)
        if form.is_valid():
            try:
                StoryService.save_story(
                    user=request.user,
                    sprint=sprint,
                    story_id=story_id,
                    cleaned_data=form.cleaned_data,
                )
            except (StoryError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Story saved.")
                return redirect("stories:story_bank")
    else:
        form = StoryEditForm(instance=story, approved_evidence_choices=choices)
    return render(request, "stories/edit.html", {"sprint": sprint, "story": story, "form": form})


@login_required
@require_POST
def story_regenerate(request, story_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        StoryService.regenerate_story(user=request.user, sprint=sprint, story_id=story_id)
    except (
        AIStoryGenerationError,
        AIStoryScoringError,
        StoryError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "Created a draft revision without overwriting the original story."
        )
    return redirect("stories:story_bank")
