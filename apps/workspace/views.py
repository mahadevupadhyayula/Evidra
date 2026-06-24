from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.matching.models import StoryMatch
from apps.opportunities.services import OpportunityService
from apps.sprints.services import SprintWorkflowService
from apps.stories.models import Story, StoryStatus
from apps.workspace.presentation import (
    build_current_opportunity_summary,
    build_next_step,
    build_recent_activity,
    build_sidebar_payment_status,
    build_sidebar_user,
    build_workflow_steps,
)


def build_dashboard_metrics(*, user, sprint, next_step):
    """Build null-safe dashboard metrics for the authenticated user's current sprint."""

    base_metrics = {
        "approved_evidence_count": 0,
        "ready_story_count": 0,
        "readiness_score": None,
        "next_step_summary": {
            "title": next_step["title"],
            "body": next_step["body"],
            "cta_label": next_step["cta_label"],
        },
    }
    if sprint is None or sprint.active_profile_id is None:
        return base_metrics

    profile = sprint.active_profile
    approved_evidence_count = EvidenceCard.objects.filter(
        user=user,
        profile=profile,
        status=EvidenceStatus.APPROVED,
    ).count()
    ready_story_count = Story.objects.filter(
        user=user,
        profile=profile,
        status__in=[StoryStatus.READY, StoryStatus.EDITED],
    ).count()
    readiness_score = StoryMatch.objects.filter(
        sprint=sprint,
        sprint__user=user,
    ).aggregate(score=Avg("total_score"))["score"]

    return {
        **base_metrics,
        "approved_evidence_count": approved_evidence_count,
        "ready_story_count": ready_story_count,
        "readiness_score": (
            round(readiness_score) if readiness_score is not None else None
        ),
    }


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
    dashboard_metrics = build_dashboard_metrics(
        user=request.user,
        sprint=sprint,
        next_step=next_step,
    )
    recent_activity = build_recent_activity(
        user=request.user,
        sprint=sprint,
        url_resolver=reverse,
    )
    sidebar_user = build_sidebar_user(request.user)
    sidebar_payment_status = build_sidebar_payment_status(
        user=request.user,
        sprint=sprint,
    )
    return render(
        request,
        "workspace/index.html",
        {
            "sprint": sprint,
            "workflow_steps": workflow_steps,
            "next_step": next_step,
            "dashboard_metrics": dashboard_metrics,
            "opportunity_summary": opportunity_summary,
            "recent_activity": recent_activity,
            "sidebar_user": sidebar_user,
            "sidebar_payment_status": sidebar_payment_status,
        },
    )


@login_required
@require_POST
def current_sprint(request):
    SprintWorkflowService.get_or_create_current_sprint(request.user)
    return redirect("workspace:index")
