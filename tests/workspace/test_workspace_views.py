import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.sprints.models import InterviewSprint, SprintState


@pytest.mark.django_db
def test_workspace_requires_authentication(client):
    response = client.get(reverse("workspace:index"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_workspace_create_current_sprint(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)

    response = client.post(reverse("workspace:current_sprint"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:index")
    sprint = InterviewSprint.objects.get(user=user)
    assert sprint.state == SprintState.DRAFT


@pytest.mark.django_db
def test_workspace_create_current_sprint_is_idempotent(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)

    client.post(reverse("workspace:current_sprint"))
    client.post(reverse("workspace:current_sprint"))

    assert InterviewSprint.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_workspace_only_displays_authenticated_users_sprint(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    viewer = User.objects.create_user(username="viewer@example.com")
    other_sprint = InterviewSprint.objects.create(user=owner)
    client.force_login(viewer)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert b"Sprint ID" not in response.content
    assert (
        f"Sprint ID</dt>\n    <dd>{other_sprint.pk}</dd>".encode()
        not in response.content
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "label", "url_name"),
    [
        (SprintState.DRAFT, "Add resume", "documents:resume_upload"),
        (SprintState.RESUME_READY, "Review profile", "profiles:profile_review"),
        (
            SprintState.PROFILE_CONFIRMED,
            "Add opportunity context",
            "opportunities:opportunity_detail",
        ),
        (
            SprintState.OPPORTUNITY_CONFIRMED,
            "Review evidence",
            "evidence:evidence_review",
        ),
        (SprintState.EVIDENCE_REVIEW, "Review evidence", "evidence:evidence_review"),
        (
            SprintState.EVIDENCE_APPROVED,
            "Generate reusable stories",
            "stories:story_bank",
        ),
        (SprintState.STORIES_READY, "Review story bank", "stories:story_bank"),
        (SprintState.MATCHING_READY, "Review readiness preview", "previews:detail"),
        (SprintState.PREVIEW_READY, "Review readiness preview", "previews:detail"),
        (SprintState.PAYMENT_PENDING, "Open Prep Kit", "prepkits:detail"),
        (SprintState.PAID, "Open Prep Kit", "prepkits:detail"),
        (SprintState.PREPKIT_READY, "Practice answers", "practice:index"),
        (SprintState.PRACTICE_ACTIVE, "Open seven-day plan", "plans:detail"),
        (SprintState.PLAN_READY, "Open seven-day plan", "plans:detail"),
    ],
)
def test_workspace_next_step_uses_link_for_navigation_ctas(
    client, state, label, url_name
):
    user = get_user_model().objects.create_user(username=f"{state}@example.com")
    InterviewSprint.objects.create(user=user, state=state)
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    expected_link = f'<a class="button-link" href="{reverse(url_name)}">{label}</a>'
    assert expected_link.encode() in response.content
    assert (
        b'<form method="post" action="/workspace/sprints/current/">'
        not in response.content
    )


@pytest.mark.django_db
def test_workspace_next_step_uses_post_form_to_create_sprint(client):
    user = get_user_model().objects.create_user(username="starter@example.com")
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert b"Create Interview Sprint" in response.content
    assert (
        f'<form method="post" action="{reverse("workspace:current_sprint")}">'.encode()
        in response.content
    )
    assert b"Your data is private and secure." in response.content


@pytest.mark.django_db
def test_workspace_displays_static_evidra_flow_explainer(client):
    user = get_user_model().objects.create_user(username="flow@example.com")
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert b"The Evidra Flow" in response.content
    assert b"Our evidence-first system." in response.content
    assert b"Real work" in response.content
    assert b"Capture outcomes and impact from your experience." in response.content
    assert b"Evidence" in response.content
    assert b"Organize and validate proof of your impact." in response.content
    assert b"Stories" in response.content
    assert b"Turn evidence into compelling interview stories." in response.content
    assert b"Prep Kit" in response.content
    assert b"Get tailored materials to prepare and practice." in response.content
    assert b"Learn more about the process" not in response.content


@pytest.mark.django_db
def test_workspace_dashboard_metrics_are_current_user_current_sprint_only(client):
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.matching.models import StoryMatch
    from apps.stories.models import Story, StoryStatus
    from tests.opportunities.helpers import make_profile_confirmed_sprint

    user, sprint, profile = make_profile_confirmed_sprint("metrics@example.com")
    other_user, other_sprint, other_profile = make_profile_confirmed_sprint(
        "other-metrics@example.com"
    )

    EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Approved owned evidence",
        source_excerpt="Owned source excerpt",
        status=EvidenceStatus.APPROVED,
    )
    EvidenceCard.objects.create(
        user=other_user,
        profile=other_profile,
        source_document=other_sprint.active_resume,
        title="Other approved evidence",
        source_excerpt="Other source excerpt",
        status=EvidenceStatus.APPROVED,
    )
    EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Draft owned evidence",
        source_excerpt="Draft source excerpt",
        status=EvidenceStatus.DRAFT,
    )

    owned_story = Story.objects.create(
        user=user,
        profile=profile,
        title="Ready owned story",
        short_answer="Short answer",
        ninety_second_answer="Ninety second answer",
        detailed_answer="Detailed answer",
        status=StoryStatus.READY,
    )
    Story.objects.create(
        user=user,
        profile=profile,
        title="Edited owned story",
        short_answer="Short answer",
        ninety_second_answer="Ninety second answer",
        detailed_answer="Detailed answer",
        status=StoryStatus.EDITED,
    )
    Story.objects.create(
        user=other_user,
        profile=other_profile,
        title="Other ready story",
        short_answer="Short answer",
        ninety_second_answer="Ninety second answer",
        detailed_answer="Detailed answer",
        status=StoryStatus.READY,
    )

    StoryMatch.objects.create(
        sprint=sprint,
        competency_key="strategy",
        competency_label="Strategy",
        primary_story=owned_story,
        total_score=80,
    )
    StoryMatch.objects.create(
        sprint=sprint,
        competency_key="execution",
        competency_label="Execution",
        primary_story=owned_story,
        total_score=60,
    )
    StoryMatch.objects.create(
        sprint=other_sprint,
        competency_key="strategy",
        competency_label="Strategy",
        total_score=100,
    )

    client.force_login(user)
    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    metrics = response.context["dashboard_metrics"]
    assert metrics["approved_evidence_count"] == 1
    assert metrics["ready_story_count"] == 2
    assert metrics["readiness_score"] == 70
    assert (
        metrics["next_step_summary"]["title"] == response.context["next_step"]["title"]
    )
    assert b"+6 this week" not in response.content


@pytest.mark.django_db
def test_workspace_dashboard_metrics_are_null_safe_without_sprint_or_profile(client):
    user = get_user_model().objects.create_user(username="null-safe@example.com")
    client.force_login(user)

    no_sprint_response = client.get(reverse("workspace:index"))

    assert no_sprint_response.status_code == 200
    assert no_sprint_response.context["dashboard_metrics"] == {
        "approved_evidence_count": 0,
        "ready_story_count": 0,
        "readiness_score": None,
        "next_step_summary": {
            "title": "Start your Interview Sprint",
            "body": "Create a Draft Interview Sprint to start the MBP workflow foundation.",
            "cta_label": "Create Interview Sprint",
        },
    }

    InterviewSprint.objects.create(user=user)
    no_profile_response = client.get(reverse("workspace:index"))

    assert no_profile_response.status_code == 200
    metrics = no_profile_response.context["dashboard_metrics"]
    assert metrics["approved_evidence_count"] == 0
    assert metrics["ready_story_count"] == 0
    assert metrics["readiness_score"] is None


@pytest.mark.django_db
def test_workspace_recent_activity_uses_owned_current_sprint_records_only(client):
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.plans.models import ImprovementPlan, ImprovementPlanStatus
    from apps.prepkits.models import PrepKit, PrepKitStatus
    from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
    from apps.stories.models import Story, StoryStatus
    from tests.opportunities.helpers import make_profile_confirmed_sprint

    user, sprint, profile = make_profile_confirmed_sprint("activity@example.com")
    other_user, other_sprint, other_profile = make_profile_confirmed_sprint(
        "other-activity@example.com"
    )

    EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Owned approved evidence title",
        source_excerpt="Owned excerpt",
        status=EvidenceStatus.APPROVED,
    )
    EvidenceCard.objects.create(
        user=other_user,
        profile=other_profile,
        source_document=other_sprint.active_resume,
        title="Led migration to AWS reducing costs by 32%",
        source_excerpt="Other excerpt",
        status=EvidenceStatus.APPROVED,
    )
    Story.objects.create(
        user=user,
        profile=profile,
        title="Owned edited story title",
        short_answer="Short answer",
        ninety_second_answer="Ninety second answer",
        detailed_answer="Detailed answer",
        status=StoryStatus.EDITED,
    )
    Story.objects.create(
        user=other_user,
        profile=other_profile,
        title="Other ready story title",
        short_answer="Short answer",
        ninety_second_answer="Ninety second answer",
        detailed_answer="Detailed answer",
        status=StoryStatus.READY,
    )
    PrepKit.objects.create(
        sprint=sprint,
        status=PrepKitStatus.READY,
        input_revision="owned-prepkit-revision",
    )
    PrepKit.objects.create(
        sprint=other_sprint,
        status=PrepKitStatus.READY,
        input_revision="other-prepkit-revision",
    )
    ReadinessPreview.objects.create(
        sprint=sprint,
        role_summary="Owned preview",
        prepkit_explanation="Owned explanation",
        input_revision="owned-preview-revision",
        status=ReadinessPreviewStatus.READY,
    )
    ReadinessPreview.objects.create(
        sprint=other_sprint,
        role_summary="Other preview",
        prepkit_explanation="Other explanation",
        input_revision="other-preview-revision",
        status=ReadinessPreviewStatus.READY,
    )
    ImprovementPlan.objects.create(
        sprint=sprint,
        status=ImprovementPlanStatus.ACTIVE,
        generated_from_revision="owned-plan-revision",
    )
    ImprovementPlan.objects.create(
        sprint=other_sprint,
        status=ImprovementPlanStatus.ACTIVE,
        generated_from_revision="other-plan-revision",
    )

    client.force_login(user)
    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    activity = response.context["recent_activity"]
    assert 3 <= len(activity) <= 5
    assert any(item["title"] == "Owned approved evidence title" for item in activity)
    assert any(item["title"] == "Owned edited story title" for item in activity)
    assert b"Owned approved evidence title" in response.content
    assert b"Owned edited story title" in response.content
    assert b"Led migration to AWS reducing costs by 32%" not in response.content
    assert b"Other ready story title" not in response.content


@pytest.mark.django_db
def test_workspace_recent_activity_empty_state_without_activity(client):
    from tests.opportunities.helpers import make_profile_confirmed_sprint

    user, _, _ = make_profile_confirmed_sprint("empty-activity@example.com")
    client.force_login(user)

    response = client.get(reverse("workspace:index"))

    assert response.status_code == 200
    assert response.context["recent_activity"] == []
    assert b"Your recent Sprint updates will appear here." in response.content
