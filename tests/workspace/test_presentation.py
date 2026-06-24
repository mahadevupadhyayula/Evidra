from apps.sprints.models import SprintState
from apps.workspace.presentation import build_workflow_steps


def test_build_workflow_steps_projects_all_visual_steps():
    steps = build_workflow_steps(SprintState.DRAFT)

    assert [(step["number"], step["label"]) for step in steps] == [
        (1, "Resume"),
        (2, "Profile"),
        (3, "Opportunity"),
        (4, "Evidence"),
        (5, "Stories"),
        (6, "Matching"),
        (7, "Preview"),
        (8, "Prep Kit"),
        (9, "Practice"),
        (10, "Plan"),
    ]


def test_build_workflow_steps_marks_current_completed_and_locked_steps():
    steps = build_workflow_steps(SprintState.EVIDENCE_REVIEW)

    assert [step["status"] for step in steps] == [
        "complete",
        "complete",
        "complete",
        "current",
        "locked",
        "locked",
        "locked",
        "locked",
        "locked",
        "locked",
    ]


def test_build_workflow_steps_uses_shared_presentation_step_for_grouped_states():
    prepkit_states = [
        SprintState.PREVIEW_READY,
        SprintState.PAYMENT_PENDING,
        SprintState.PAID,
    ]

    for state in prepkit_states:
        steps = build_workflow_steps(state)

        assert steps[7]["label"] == "Prep Kit"
        assert steps[7]["status"] == "current"


def test_build_workflow_steps_only_sets_urls_for_reachable_steps():
    steps = build_workflow_steps(
        SprintState.PROFILE_CONFIRMED,
        url_resolver=lambda url_name: f"/{url_name}/",
    )

    assert steps[0]["target_url"] == "/documents:resume_upload/"
    assert steps[1]["target_url"] == "/profiles:profile_review/"
    assert steps[2]["target_url"] == "/opportunities:opportunity_detail/"
    assert steps[3]["target_url"] is None
