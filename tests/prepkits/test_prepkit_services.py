import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.matching.models import StoryMatch
from apps.matching.services import MatchingService
from apps.opportunities.models import Opportunity
from apps.payments.models import Payment
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.prepkits.services import PrepKitError, PrepKitService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from tests.prepkits.helpers import make_paid_sprint


@pytest.mark.django_db
def test_generate_prepkit_creates_ready_artifact_and_transitions():
    user, sprint = make_paid_sprint()

    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )

    sprint.refresh_from_db()
    assert prepkit.status == PrepKitStatus.READY
    assert prepkit.role_briefing["briefing"]
    assert len(prepkit.seven_day_plan) == 7
    assert sprint.state == SprintState.PREPKIT_READY


@pytest.mark.django_db
def test_generate_prepkit_requires_verified_payment():
    user, sprint = make_paid_sprint("unpaid-prepkit@example.com")
    Payment.objects.filter(user=user, sprint=sprint).delete()

    with pytest.raises(SprintTransitionConditionMissing, match="Verified payment"):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
        )


@pytest.mark.django_db
def test_generate_prepkit_rejects_unpaid_state():
    user, sprint = make_paid_sprint("pending-prepkit@example.com")
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(InvalidSprintTransition):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
        )


@pytest.mark.django_db
def test_generate_prepkit_is_idempotent_for_same_revision():
    user, sprint = make_paid_sprint("idempotent-prepkit@example.com")
    service = EvidraAIService(client=MockAIClient())

    first = PrepKitService.generate_prepkit(user=user, sprint=sprint, ai_service=service)
    second = PrepKitService.generate_prepkit(user=user, sprint=sprint, ai_service=service)

    assert first.pk == second.pk
    assert PrepKit.objects.filter(sprint=sprint, status=PrepKitStatus.READY).count() == 1


@pytest.mark.django_db
def test_generate_prepkit_rejects_cross_user_sprint():
    _user, sprint = make_paid_sprint("owner-prepkit@example.com")
    other = get_user_model().objects.create_user(username="other-prepkit@example.com")

    with pytest.raises(SprintOwnershipError):
        PrepKitService.generate_prepkit(
            user=other, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
        )


@pytest.mark.django_db
def test_invalid_ai_output_marks_failed_and_preserves_paid_state():
    user, sprint = make_paid_sprint("failed-prepkit@example.com")
    client = MockAIClient(responses=[{"role_briefing_points": []}, {}])

    with pytest.raises(RuntimeError):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAID
    assert PrepKit.objects.filter(sprint=sprint, status=PrepKitStatus.FAILED).exists()


@pytest.mark.django_db
def test_generate_prepkit_rejects_unapproved_evidence_reference():
    user, sprint = make_paid_sprint("bad-ref-prepkit@example.com")
    bad = MockAIClient()
    analysis = bad.generate_prepkit_analysis(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
    )
    artifact = bad.generate_prepkit_artifact(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1, "competency_key": "x"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
        analysis=analysis,
    )
    artifact["question_bank"][0]["evidence_ids"] = [999999]
    client = MockAIClient(responses=[analysis, artifact])

    with pytest.raises(PrepKitError):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )


@pytest.mark.django_db
def test_current_prepkit_marks_changed_inputs_stale():
    user, sprint = make_paid_sprint("stale-prepkit@example.com")
    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    opportunity = Opportunity.objects.get(sprint=sprint)
    opportunity.concerns = "New concern after generation"
    opportunity.save(update_fields=["concerns", "updated_at"])

    current = PrepKitService.current_prepkit(user=user, sprint=sprint)

    prepkit.refresh_from_db()
    assert current is None
    assert prepkit.status == PrepKitStatus.STALE


@pytest.mark.django_db
def test_mark_prepkit_ready_rejects_stale_revision():
    user, sprint = make_paid_sprint("stale-transition-prepkit@example.com")
    prepkit = PrepKit.objects.create(
        sprint=sprint,
        input_revision="not-current",
        status=PrepKitStatus.READY,
        generated_at=timezone.now(),
    )

    with pytest.raises(SprintTransitionConditionMissing, match="current Prep Kit"):
        SprintWorkflowService.mark_prepkit_ready(user=user, sprint=sprint, prepkit=prepkit)


@pytest.mark.django_db
def test_generate_prepkit_rejects_unknown_recommended_story_id():
    user, sprint = make_paid_sprint("bad-recommended-story@example.com")
    bad = MockAIClient()
    analysis = bad.generate_prepkit_analysis(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
    )
    artifact = bad.generate_prepkit_artifact(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1, "competency_key": "x"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
        analysis=analysis,
    )
    artifact["question_bank"][0]["recommended_story_id"] = 999999
    client = MockAIClient(responses=[analysis, artifact])

    with pytest.raises(PrepKitError, match="recommended story"):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )


@pytest.mark.django_db
def test_generate_prepkit_rejects_unsupported_source_excerpt():
    user, sprint = make_paid_sprint("bad-source-excerpt@example.com")
    bad = MockAIClient()
    analysis = bad.generate_prepkit_analysis(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
    )
    artifact = bad.generate_prepkit_artifact(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1, "competency_key": "x"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
        analysis=analysis,
    )
    artifact["role_briefing"]["source_refs"] = [
        {
            "source_type": "opportunity",
            "source_field": "job_description",
            "excerpt": "not in the confirmed opportunity",
        }
    ]
    client = MockAIClient(responses=[analysis, artifact])

    with pytest.raises(PrepKitError, match="source excerpt"):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )


@pytest.mark.django_db
def test_generate_prepkit_rejects_empty_non_record_source_ref():
    user, sprint = make_paid_sprint("empty-source-ref@example.com")
    bad = MockAIClient()
    analysis = bad.generate_prepkit_analysis(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
    )
    artifact = bad.generate_prepkit_artifact(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1, "competency_key": "x"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
        analysis=analysis,
    )
    artifact["role_briefing"]["source_refs"] = [{"source_type": "opportunity"}]
    client = MockAIClient(responses=[analysis, artifact])

    with pytest.raises(PrepKitError, match="identify source material"):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )


@pytest.mark.django_db
def test_generate_prepkit_rejects_missing_company_context_source_ref():
    user, sprint = make_paid_sprint("missing-company-source@example.com")
    bad = MockAIClient()
    analysis = bad.generate_prepkit_analysis(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
    )
    artifact = bad.generate_prepkit_artifact(
        opportunity_context={"role_title": "Role"},
        role_pack={},
        matches=[{"id": 1, "competency_key": "x"}],
        stories=[{"id": 1}],
        approved_evidence=[{"id": 1}],
        preview={},
        analysis=analysis,
    )
    artifact["role_briefing"]["source_refs"] = [
        {"source_type": "company_context", "source_field": "company_description"}
    ]
    client = MockAIClient(responses=[analysis, artifact])

    with pytest.raises(PrepKitError, match="missing source material"):
        PrepKitService.generate_prepkit(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )


@pytest.mark.django_db
def test_current_prepkit_marks_stale_when_current_inputs_are_missing():
    user, sprint = make_paid_sprint("missing-inputs-stale@example.com")
    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    StoryMatch.objects.filter(sprint=sprint).delete()

    current = PrepKitService.current_prepkit(user=user, sprint=sprint)

    prepkit.refresh_from_db()
    assert current is None
    assert prepkit.status == PrepKitStatus.STALE


@pytest.mark.django_db
def test_matching_override_marks_ready_prepkit_stale():
    user, sprint = make_paid_sprint("override-stales-prepkit@example.com")
    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    match = StoryMatch.objects.filter(sprint=sprint, alternative_story__isnull=False).first()
    assert match is not None
    sprint.state = SprintState.MATCHING_READY
    sprint.save(update_fields=["state", "updated_at"])

    MatchingService.set_user_override(
        user=user, sprint=sprint, match_id=match.id, story_id=match.alternative_story_id
    )

    prepkit.refresh_from_db()
    assert prepkit.status == PrepKitStatus.STALE


@pytest.mark.django_db
def test_mark_prepkit_ready_rejects_failed_artifact():
    user, sprint = make_paid_sprint("failed-transition@example.com")
    prepkit = PrepKit.objects.create(
        sprint=sprint, input_revision="rev", status=PrepKitStatus.FAILED
    )

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_prepkit_ready(user=user, sprint=sprint, prepkit=prepkit)
