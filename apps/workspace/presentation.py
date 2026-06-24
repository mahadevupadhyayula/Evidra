from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from apps.sprints.models import SprintState


def build_sidebar_user(user) -> dict[str, str]:
    """Build sidebar account identity from authenticated user fields only."""

    full_name = user.get_full_name().strip()
    display_name = full_name or user.email or user.username
    return {
        "display_name": display_name,
        "email": user.email,
    }


def build_sidebar_payment_status(*, user, sprint) -> dict[str, str] | None:
    """Build neutral Prep Kit entitlement copy from owned current-Sprint payments."""

    if sprint is None:
        return None

    from apps.payments.models import Payment, PaymentStatus

    has_paid_entitlement = Payment.objects.filter(
        user=user,
        sprint=sprint,
        status=PaymentStatus.PAID,
    ).exists()
    if has_paid_entitlement:
        return {
            "label": "Prep Kit unlocked",
            "body": "Paid Prep Kit is available for this Sprint.",
        }
    return {
        "label": "Prep Kit locked",
        "body": "Prep Kit unlocks after verified payment in the MBP flow.",
    }


def count_completed_workflow_steps(workflow_steps: list[dict[str, object]]) -> int:
    """Count completed presentation steps from the deterministic workflow tracker."""

    return sum(1 for step in workflow_steps if step["status"] == "complete")


def build_current_opportunity_summary(
    opportunity, workflow_steps: list[dict[str, object]]
) -> dict[str, object] | None:
    """Build the workspace summary for the current non-stale opportunity."""

    if opportunity is None:
        return None

    return {
        "role_title": opportunity.role_title,
        "company_name": opportunity.company_name,
        "target_seniority": opportunity.target_seniority,
        "role_family": opportunity.get_role_family_display(),
        "interview_stage": opportunity.interview_stage,
        "interview_date": opportunity.interview_date,
        "confirmation_status": opportunity.get_confirmation_status_display(),
        "status_label": "Active",
        "completed_steps": count_completed_workflow_steps(workflow_steps),
        "total_steps": len(workflow_steps),
    }


@dataclass(frozen=True)
class WorkflowStepDefinition:
    number: int
    label: str
    state: str
    url_name: str | None = None


WORKFLOW_STEP_DEFINITIONS = (
    WorkflowStepDefinition(1, "Resume", "resume", "documents:resume_upload"),
    WorkflowStepDefinition(2, "Profile", "profile", "profiles:profile_review"),
    WorkflowStepDefinition(3, "Opportunity", "opportunity", "opportunities:opportunity_detail"),
    WorkflowStepDefinition(4, "Evidence", "evidence", "evidence:evidence_review"),
    WorkflowStepDefinition(5, "Stories", "stories", "stories:story_bank"),
    WorkflowStepDefinition(6, "Matching", "matching", "matching:index"),
    WorkflowStepDefinition(7, "Preview", "preview", "previews:detail"),
    WorkflowStepDefinition(8, "Prep Kit", "prepkit", "prepkits:detail"),
    WorkflowStepDefinition(9, "Practice", "practice", "practice:index"),
    WorkflowStepDefinition(10, "Plan", "plan", "plans:detail"),
)

SPRINT_STATE_TO_WORKFLOW_STEP = {
    SprintState.DRAFT: 1,
    SprintState.RESUME_READY: 2,
    SprintState.PROFILE_CONFIRMED: 3,
    SprintState.OPPORTUNITY_CONFIRMED: 4,
    SprintState.EVIDENCE_REVIEW: 4,
    SprintState.EVIDENCE_APPROVED: 5,
    SprintState.STORIES_READY: 6,
    SprintState.MATCHING_READY: 7,
    SprintState.PREVIEW_READY: 8,
    SprintState.PAYMENT_PENDING: 8,
    SprintState.PAID: 8,
    SprintState.PREPKIT_READY: 9,
    SprintState.PRACTICE_ACTIVE: 9,
    SprintState.PLAN_READY: 10,
    SprintState.COMPLETED: 10,
}


def build_workflow_steps(
    sprint_state: SprintState | str | None,
    *,
    url_resolver: Callable[[str], str] | None = None,
) -> list[dict[str, object]]:
    """Project deterministic Sprint states onto presentation-only workspace steps."""

    current_step_number = SPRINT_STATE_TO_WORKFLOW_STEP.get(sprint_state)
    steps = []

    for step in WORKFLOW_STEP_DEFINITIONS:
        if current_step_number is None:
            status = "locked"
        elif step.number < current_step_number:
            status = "complete"
        elif step.number == current_step_number:
            status = "current"
        else:
            status = "locked"

        target_url = None
        if url_resolver is not None and step.url_name is not None and status != "locked":
            target_url = url_resolver(step.url_name)

        steps.append(
            {
                "label": step.label,
                "number": step.number,
                "status": status,
                "target_url": target_url,
            }
        )

    return steps


def build_recent_activity(
    *, user, sprint, url_resolver: Callable[[str], str], limit: int = 5
) -> list[dict[str, object]]:
    """Build a derived recent activity list from owned current Sprint records."""

    if sprint is None:
        return []

    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.plans.models import ImprovementPlan, ImprovementPlanStatus
    from apps.prepkits.models import PrepKit, PrepKitStatus
    from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
    from apps.stories.models import Story, StoryStatus

    activity: list[dict[str, object]] = []

    if sprint.active_profile_id is not None:
        activity.extend(
            {
                "label": "Evidence approved",
                "title": evidence.title,
                "timestamp": evidence.updated_at,
                "target_url": url_resolver("evidence:evidence_review"),
                "type": "evidence",
            }
            for evidence in EvidenceCard.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status=EvidenceStatus.APPROVED,
            ).only("title", "updated_at")[:limit]
        )
        activity.extend(
            {
                "label": "Story ready" if story.status == StoryStatus.READY else "Story edited",
                "title": story.title,
                "timestamp": story.updated_at,
                "target_url": url_resolver("stories:story_bank"),
                "type": "story",
            }
            for story in Story.objects.filter(
                user=user,
                profile=sprint.active_profile,
                status__in=[StoryStatus.READY, StoryStatus.EDITED],
            ).only("title", "status", "updated_at")[:limit]
        )

    current_prep_kit_statuses = [PrepKitStatus.PENDING, PrepKitStatus.READY]
    activity.extend(
        {
            "label": "Prep Kit current",
            "title": prep_kit.get_status_display(),
            "timestamp": prep_kit.updated_at,
            "target_url": url_resolver("prepkits:detail"),
            "type": "prepkit",
        }
        for prep_kit in PrepKit.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status__in=current_prep_kit_statuses,
        ).only("status", "updated_at")[:limit]
    )

    current_preview_statuses = [ReadinessPreviewStatus.DRAFT, ReadinessPreviewStatus.READY]
    activity.extend(
        {
            "label": "Readiness preview current",
            "title": preview.get_status_display(),
            "timestamp": preview.updated_at,
            "target_url": url_resolver("previews:detail"),
            "type": "preview",
        }
        for preview in ReadinessPreview.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status__in=current_preview_statuses,
        ).only("status", "updated_at")[:limit]
    )

    current_plan_statuses = [ImprovementPlanStatus.DRAFT, ImprovementPlanStatus.ACTIVE]
    activity.extend(
        {
            "label": "Improvement plan current",
            "title": plan.get_status_display(),
            "timestamp": plan.updated_at,
            "target_url": url_resolver("plans:detail"),
            "type": "plan",
        }
        for plan in ImprovementPlan.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status__in=current_plan_statuses,
        ).only("status", "updated_at")[:limit]
    )

    return sorted(activity, key=lambda item: item["timestamp"], reverse=True)[:limit]


def build_next_step(
    user,
    sprint,
    *,
    url_resolver: Callable[[str], str],
) -> dict[str, str]:
    """Build the primary workspace next-step CTA for the authenticated user."""

    del user  # Ownership is established by the caller's authenticated Sprint query.

    base = {
        "eyebrow": "Recommended next step",
        "reassurance": "Your data is private and secure.",
    }

    if sprint is None:
        return {
            **base,
            "title": "Start your Interview Sprint",
            "body": "Create a Draft Interview Sprint to start the MBP workflow foundation.",
            "cta_label": "Create Interview Sprint",
            "cta_url": url_resolver("workspace:current_sprint"),
            "cta_method": "post",
        }

    state = sprint.state
    state_steps = {
        SprintState.DRAFT: {
            "title": "Add your resume",
            "body": "Next step: add and confirm your resume.",
            "cta_label": "Add resume",
            "url_name": "documents:resume_upload",
        },
        SprintState.RESUME_READY: {
            "title": "Review your career profile",
            "body": "Your resume is confirmed. Review and confirm your career profile next.",
            "cta_label": "Review profile",
            "url_name": "profiles:profile_review",
        },
        SprintState.PROFILE_CONFIRMED: {
            "title": "Add opportunity context",
            "body": "Your career profile is confirmed. Add opportunity context next.",
            "cta_label": "Add opportunity context",
            "url_name": "opportunities:opportunity_detail",
        },
        SprintState.OPPORTUNITY_CONFIRMED: {
            "title": "Review career evidence",
            "body": "Your opportunity is confirmed. Review and approve career evidence next.",
            "cta_label": "Review evidence",
            "url_name": "evidence:evidence_review",
        },
        SprintState.EVIDENCE_REVIEW: {
            "title": "Review career evidence",
            "body": "Your opportunity is confirmed. Review and approve career evidence next.",
            "cta_label": "Review evidence",
            "url_name": "evidence:evidence_review",
        },
        SprintState.EVIDENCE_APPROVED: {
            "title": "Generate reusable stories",
            "body": "Your evidence is approved. Generate reusable interview stories next.",
            "cta_label": "Generate reusable stories",
            "url_name": "stories:story_bank",
        },
        SprintState.STORIES_READY: {
            "title": "Review your story bank",
            "body": "Your reusable story bank is ready.",
            "cta_label": "Review story bank",
            "url_name": "stories:story_bank",
        },
        SprintState.MATCHING_READY: {
            "title": "Review readiness preview",
            "body": "Your readiness preview is ready or in progress.",
            "cta_label": "Review readiness preview",
            "url_name": "previews:detail",
        },
        SprintState.PREVIEW_READY: {
            "title": "Review readiness preview",
            "body": "Your readiness preview is ready or in progress.",
            "cta_label": "Review readiness preview",
            "url_name": "previews:detail",
        },
        SprintState.PAYMENT_PENDING: {
            "title": "Open your Prep Kit",
            "body": "Your payment and Prep Kit are in progress.",
            "cta_label": "Open Prep Kit",
            "url_name": "prepkits:detail",
        },
        SprintState.PAID: {
            "title": "Open your Prep Kit",
            "body": "Your payment and Prep Kit are in progress.",
            "cta_label": "Open Prep Kit",
            "url_name": "prepkits:detail",
        },
        SprintState.PREPKIT_READY: {
            "title": "Practice answers",
            "body": "Your Prep Kit is ready. Complete text practice next.",
            "cta_label": "Practice answers",
            "url_name": "practice:index",
        },
        SprintState.PRACTICE_ACTIVE: {
            "title": "Open your seven-day plan",
            "body": "Your practice is active. Generate or follow your seven-day plan next.",
            "cta_label": "Open seven-day plan",
            "url_name": "plans:detail",
        },
        SprintState.PLAN_READY: {
            "title": "Open your seven-day plan",
            "body": "Your practice is active. Generate or follow your seven-day plan next.",
            "cta_label": "Open seven-day plan",
            "url_name": "plans:detail",
        },
    }

    step = state_steps[state]
    return {
        **base,
        "title": step["title"],
        "body": step["body"],
        "cta_label": step["cta_label"],
        "cta_url": url_resolver(step["url_name"]),
        "cta_method": "get",
    }
