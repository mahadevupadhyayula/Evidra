import pytest
from django.http import Http404

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.documents.services import ResumeDocumentService
from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.evidence.services import EvidenceService
from apps.matching.services import MatchingService
from apps.opportunities.services import OpportunityService
from apps.payments.services import RazorpayPaymentService
from apps.plans.models import PlanTask
from apps.plans.services import ImprovementPlanService
from apps.practice.services import PracticeService
from apps.prepkits.services import PrepKitService
from apps.previews.services import ReadinessPreviewService
from apps.profiles.services import CareerProfileService
from apps.sprints.services import SprintOwnershipError, SprintWorkflowService
from apps.stories.models import Story, StoryStatus
from apps.stories.services import StoryService
from tests.matching.helpers import make_stories_ready_sprint
from tests.opportunities.helpers import make_profile_confirmed_sprint, opportunity_data
from tests.payments.helpers import PAYMENT_SETTINGS, make_preview_ready_sprint
from tests.plans.helpers import make_plan_ready_inputs
from tests.practice.helpers import make_practice_ready_sprint
from tests.prepkits.helpers import make_paid_sprint
from tests.previews.helpers import make_matching_ready_sprint
from tests.stories.helpers import make_evidence_approved_sprint


@pytest.mark.django_db
def test_cross_user_resume_profile_and_opportunity_records_are_rejected(django_user_model):
    owner, sprint, profile = make_profile_confirmed_sprint("early-owner-stage5c@example.com")
    opportunity = OpportunityService.get_or_create_draft_opportunity(user=owner, sprint=sprint)
    attacker = django_user_model.objects.create_user("early-attacker-stage5c@example.com")

    with pytest.raises(Http404):
        SprintWorkflowService.get_owned_sprint(attacker, sprint.id)
    with pytest.raises(Http404):
        ResumeDocumentService.get_owned_document(attacker, sprint.active_resume_id)
    with pytest.raises(Http404):
        ResumeDocumentService.confirm_resume(
            user=attacker, sprint=sprint, document_id=sprint.active_resume_id
        )
    with pytest.raises(Http404):
        CareerProfileService.get_owned_profile(attacker, profile.id)
    with pytest.raises(SprintOwnershipError):
        CareerProfileService.confirm_profile(
            user=attacker, sprint=sprint, profile_id=profile.id, cleaned_data={}
        )
    with pytest.raises(Http404):
        OpportunityService.get_owned_opportunity(attacker, opportunity.id)
    with pytest.raises(SprintOwnershipError):
        OpportunityService.analyze_and_save_opportunity(
            user=attacker,
            sprint=sprint,
            cleaned_data=opportunity_data(),
        )
    with pytest.raises(SprintOwnershipError):
        OpportunityService.confirm_opportunity(
            user=attacker, sprint=sprint, opportunity_id=opportunity.id
        )

    sprint.refresh_from_db()
    assert sprint.user == owner


@pytest.mark.django_db
def test_cross_user_evidence_story_matching_and_preview_records_are_rejected(django_user_model):
    owner, sprint, profile = make_evidence_approved_sprint("middle-owner-stage5c@example.com")
    card = EvidenceCard.objects.filter(user=owner, profile=profile).first()
    attacker = django_user_model.objects.create_user("middle-attacker-stage5c@example.com")

    with pytest.raises(SprintOwnershipError):
        EvidenceService.list_cards(user=attacker, sprint=sprint)
    with pytest.raises(SprintOwnershipError):
        EvidenceService.approve_card(user=attacker, sprint=sprint, card_id=card.id)
    assert EvidenceCard.objects.get(pk=card.id).status == EvidenceStatus.APPROVED

    story = Story.objects.create(
        user=owner,
        profile=profile,
        title="Owned story",
        short_answer="Short",
        ninety_second_answer="Medium",
        detailed_answer="Detailed",
        evidence_ids=[card.id],
        status=StoryStatus.READY,
    )
    with pytest.raises(SprintOwnershipError):
        StoryService.get_owned_story(user=attacker, sprint=sprint, story_id=story.id)
    with pytest.raises(SprintOwnershipError):
        StoryService.generate_stories(user=attacker, sprint=sprint)

    match_owner, match_sprint, _profile, _evidence, story, _alternative = make_stories_ready_sprint(
        "match-owner-stage5c@example.com"
    )
    matches = MatchingService.generate_matches(
        user=match_owner, sprint=match_sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    match_sprint.refresh_from_db()
    with pytest.raises(SprintOwnershipError):
        MatchingService.list_matches(user=attacker, sprint=match_sprint)
    with pytest.raises(SprintOwnershipError):
        MatchingService.set_user_override(
            user=attacker, sprint=match_sprint, match_id=matches[0].id, story_id=story.id
        )

    preview_owner, preview_sprint, *_rest = make_matching_ready_sprint(
        "preview-owner-stage5c@example.com"
    )
    with pytest.raises(SprintOwnershipError):
        ReadinessPreviewService.current_preview(user=attacker, sprint=preview_sprint)
    with pytest.raises(SprintOwnershipError):
        ReadinessPreviewService.generate_preview(user=attacker, sprint=preview_sprint)

    assert sprint.user == owner
    assert match_sprint.user == match_owner
    assert preview_sprint.user == preview_owner


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_cross_user_payment_checkout_is_rejected(django_user_model):
    _owner, sprint = make_preview_ready_sprint("payment-owner-stage5c@example.com")
    attacker = django_user_model.objects.create_user("payment-attacker-stage5c@example.com")

    with pytest.raises(SprintOwnershipError):
        RazorpayPaymentService().create_or_reuse_order(user=attacker, sprint=sprint)


@pytest.mark.django_db
def test_cross_user_paid_artifacts_are_not_visible_or_regenerated(django_user_model):
    _owner, sprint = make_paid_sprint("paid-owner-stage5c@example.com")
    attacker = django_user_model.objects.create_user("paid-attacker-stage5c@example.com")

    with pytest.raises(SprintOwnershipError):
        PrepKitService.current_prepkit(user=attacker, sprint=sprint)
    with pytest.raises(SprintOwnershipError):
        PrepKitService.generate_prepkit(user=attacker, sprint=sprint)


@pytest.mark.django_db
def test_cross_user_practice_history_and_submission_are_rejected(django_user_model):
    owner, sprint, prepkit = make_practice_ready_sprint("practice-owner-stage5c@example.com")
    attacker = django_user_model.objects.create_user("practice-attacker-stage5c@example.com")

    with pytest.raises(SprintOwnershipError):
        SprintWorkflowService.mark_prepkit_ready(user=attacker, sprint=sprint, prepkit=prepkit)
    with pytest.raises(SprintOwnershipError):
        PracticeService.attempt_history(user=attacker, sprint=sprint)
    with pytest.raises(SprintOwnershipError):
        PracticeService.submit_answer(
            user=attacker,
            sprint=sprint,
            question_id=prepkit.question_bank[0].get("id", "q1"),
            answer_text="I led the approved work and explained the result clearly.",
        )

    sprint.refresh_from_db()
    assert sprint.user == owner


@pytest.mark.django_db
def test_cross_user_plan_task_update_and_completion_are_rejected(django_user_model):
    _owner, sprint, _prepkit, _attempt = make_plan_ready_inputs("plan-owner-stage5c@example.com")
    plan = ImprovementPlanService.generate_plan(user=sprint.user, sprint=sprint)
    task = PlanTask.objects.filter(plan=plan).first()
    attacker = django_user_model.objects.create_user("plan-attacker-stage5c@example.com")

    with pytest.raises(SprintOwnershipError):
        ImprovementPlanService.set_task_status(
            user=attacker, sprint=sprint, task_id=task.id, status="DONE"
        )
    with pytest.raises(SprintOwnershipError):
        ImprovementPlanService.complete_sprint(user=attacker, sprint=sprint)
