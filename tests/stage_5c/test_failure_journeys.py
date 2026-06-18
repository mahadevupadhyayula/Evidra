import pytest

from apps.payments.models import PaymentStatus
from apps.payments.services import PaymentProcessingError, RazorpayPaymentService
from apps.plans.models import ImprovementPlan
from apps.plans.services import ImprovementPlanService
from apps.practice.models import PracticeAttempt
from apps.practice.services import PracticeError, PracticeService
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.prepkits.services import PrepKitService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from tests.payments.helpers import (
    PAYMENT_SETTINGS,
    FakeRazorpayClient,
    make_preview_ready_sprint,
    sign,
    webhook_body,
)
from tests.plans.helpers import make_plan_ready_inputs
from tests.practice.helpers import make_practice_ready_sprint
from tests.prepkits.helpers import make_paid_sprint


@pytest.mark.django_db
def test_forbidden_workflow_transitions_preserve_state():
    user, sprint = make_paid_sprint("forbidden-stage5c@example.com")
    with pytest.raises(InvalidSprintTransition):
        SprintWorkflowService.transition(user=user, sprint=sprint, to_state=SprintState.COMPLETED)
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAID


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_payment_redirect_does_not_unlock_paid_access():
    user, sprint = make_preview_ready_sprint("redirect-stage5c@example.com")
    payment = RazorpayPaymentService(
        client=FakeRazorpayClient(order_id="order_redirect")
    ).create_or_reuse_order(user=user, sprint=sprint)
    payment.provider_payment_id = "browser_redirect_claim"
    payment.save(update_fields=["provider_payment_id", "updated_at"])

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_paid(user=user, sprint=sprint, payment=payment)
    sprint.refresh_from_db()
    payment.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING
    assert payment.status == PaymentStatus.ORDER_CREATED


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_invalid_webhook_preserves_payment_pending_and_duplicate_success_is_idempotent():
    user, sprint = make_preview_ready_sprint("webhook-stage5c@example.com")
    service = RazorpayPaymentService(client=FakeRazorpayClient(order_id="order_webhook"))
    payment = service.create_or_reuse_order(user=user, sprint=sprint)
    bad_body = webhook_body(order_id="order_webhook", amount=payment.amount + 100)

    with pytest.raises(PaymentProcessingError):
        service.process_webhook(raw_body=bad_body, signature=sign(bad_body))
    sprint.refresh_from_db()
    payment.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING
    assert payment.status == PaymentStatus.ORDER_CREATED

    good_body = webhook_body(
        order_id="order_webhook", payment_id="pay_webhook", event_id="evt_webhook"
    )
    first = service.process_webhook(raw_body=good_body, signature=sign(good_body))
    second = service.process_webhook(raw_body=good_body, signature=sign(good_body))
    sprint.refresh_from_db()
    assert first.processed is True
    assert second.duplicate is True
    assert sprint.state == SprintState.PAID


@pytest.mark.django_db
def test_prepkit_generation_failure_preserves_paid_entitlement():
    class FailingAIService:
        def generate_prepkit_analysis(self, **kwargs):
            raise RuntimeError("AI unavailable")

    user, sprint = make_paid_sprint("prepkit-failure-stage5c@example.com")
    with pytest.raises(RuntimeError):
        PrepKitService.generate_prepkit(user=user, sprint=sprint, ai_service=FailingAIService())
    sprint.refresh_from_db()
    failed = PrepKit.objects.get(sprint=sprint)
    assert sprint.state == SprintState.PAID
    assert failed.status == PrepKitStatus.FAILED


@pytest.mark.django_db
def test_invalid_practice_answer_does_not_create_attempt():
    user, sprint, prepkit = make_practice_ready_sprint("invalid-practice-stage5c@example.com")
    with pytest.raises(PracticeError):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id=PracticeService.priority_questions(
                user=user, sprint=sprint, prepkit=prepkit
            )[0]["question_id"],
            answer_text="too short",
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREPKIT_READY


@pytest.mark.django_db
def test_plan_generation_and_completion_reject_wrong_states():
    user, sprint, _prepkit = make_practice_ready_sprint("plan-reject-stage5c@example.com")
    with pytest.raises(InvalidSprintTransition):
        ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    assert ImprovementPlan.objects.filter(sprint=sprint).count() == 0

    user2, sprint2, _prepkit2, _attempt = make_plan_ready_inputs(
        "completion-reject-stage5c@example.com"
    )
    with pytest.raises(SprintTransitionConditionMissing):
        ImprovementPlanService.complete_sprint(user=user2, sprint=sprint2)
    sprint2.refresh_from_db()
    assert sprint2.state == SprintState.PRACTICE_ACTIVE

@pytest.mark.django_db
def test_ai_story_generation_rejects_unapproved_evidence_references():
    from ai.client import MockAIClient
    from ai.services import AIStoryGenerationError, EvidraAIService
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.stories.models import Story
    from apps.stories.services import StoryService
    from tests.stories.helpers import generated_story, make_evidence_approved_sprint

    user, sprint, _profile = make_evidence_approved_sprint("ai-story-stage5c@example.com")
    draft = EvidenceCard.objects.create(
        user=user,
        profile=sprint.active_profile,
        source_document=sprint.active_resume,
        title="Unapproved draft evidence",
        action="Led unapproved work",
        result="Unapproved result",
        source_excerpt="Experience leading product teams and delivering customer outcomes.",
        status=EvidenceStatus.DRAFT,
    )
    client = MockAIClient(
        responses=[
            {"stories": [generated_story(draft.id)]},
            {"stories": [generated_story(draft.id)]},
        ]
    )

    with pytest.raises(AIStoryGenerationError):
        StoryService.generate_stories(
            user=user, sprint=sprint, ai_service=EvidraAIService(client=client)
        )
    assert Story.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_ai_matching_discards_unapproved_evidence_references():
    from ai.client import MockAIClient
    from ai.services import EvidraAIService
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.matching.models import StoryMatch
    from apps.matching.services import MatchingService
    from tests.matching.helpers import make_stories_ready_sprint, match_response

    user, sprint, _profile, evidence, story, _alternative = make_stories_ready_sprint(
        "ai-matching-stage5c@example.com"
    )
    unapproved = EvidenceCard.objects.create(
        user=user,
        profile=sprint.active_profile,
        source_document=sprint.active_resume,
        title="Unapproved match evidence",
        source_excerpt="Experience leading product teams and delivering customer outcomes.",
        status=EvidenceStatus.DRAFT,
    )
    response = match_response(story, evidence)
    response["matches"][0]["evidence_ids"] = [evidence.id, unapproved.id]

    matches = MatchingService.generate_matches(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
    )

    assert StoryMatch.objects.filter(sprint=sprint).count() == len(matches)
    assert all(unapproved.id not in match.evidence_ids for match in matches)


@pytest.mark.django_db
def test_preview_generation_rejects_unapproved_evidence_references():
    from ai.client import MockAIClient
    from ai.services import EvidraAIService
    from apps.evidence.models import EvidenceCard, EvidenceStatus
    from apps.previews.models import ReadinessPreview
    from apps.previews.services import ReadinessPreviewError, ReadinessPreviewService
    from tests.previews.helpers import make_matching_ready_sprint, preview_response

    user, sprint, profile, evidence, story, _alternative, match = make_matching_ready_sprint(
        "ai-preview-stage5c@example.com"
    )
    unapproved = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Unapproved evidence",
        action="Unapproved action",
        result="Unapproved result",
        source_excerpt="Experience leading product teams and delivering customer outcomes.",
        status=EvidenceStatus.DRAFT,
    )
    response = preview_response(match, story, evidence)
    response["matched_story_excerpt"]["evidence_ids"] = [unapproved.id]

    with pytest.raises(ReadinessPreviewError):
        ReadinessPreviewService.generate_preview(
            user=user,
            sprint=sprint,
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert ReadinessPreview.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_prepkit_generation_preserves_source_references_and_paid_state():
    from ai.client import MockAIClient
    from ai.services import EvidraAIService
    from apps.prepkits.models import PrepKitStatus
    from tests.prepkits.helpers import make_paid_sprint

    user, sprint = make_paid_sprint("ai-prepkit-stage5c@example.com")

    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREPKIT_READY
    assert prepkit.status == PrepKitStatus.READY
    grounded_items = [
        prepkit.role_briefing,
        *prepkit.fit_summary["strengths"],
        *prepkit.competency_coverage,
        *prepkit.story_map,
        *prepkit.question_bank,
        *prepkit.practice_priorities,
    ]
    assert all(item.get("source_refs") for item in grounded_items)
