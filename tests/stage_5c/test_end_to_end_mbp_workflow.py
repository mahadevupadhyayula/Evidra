import pytest

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.documents.models import DocumentParsingStatus
from apps.documents.services import ResumeDocumentService
from apps.evidence.models import EvidenceCard
from apps.evidence.services import EvidenceService
from apps.matching.services import MatchingService
from apps.opportunities.models import CompanyContextStatus
from apps.opportunities.services import OpportunityService
from apps.payments.models import PaymentStatus
from apps.payments.services import RazorpayPaymentService
from apps.plans.models import ImprovementPlanStatus, PlanTask
from apps.plans.services import ImprovementPlanService
from apps.practice.models import PracticeAttempt
from apps.practice.services import PracticeService
from apps.prepkits.services import PrepKitService
from apps.previews.services import ReadinessPreviewService
from apps.profiles.models import CareerProfileStatus
from apps.profiles.services import CareerProfileService
from apps.sprints.models import SprintState
from apps.sprints.services import SprintWorkflowService
from apps.stories.models import StoryStatus
from apps.stories.services import StoryService
from tests.opportunities.helpers import opportunity_data
from tests.payments.helpers import PAYMENT_SETTINGS, FakeRazorpayClient, sign, webhook_body

RESUME_TEXT = (
    "Stage Five C led product strategy for customer onboarding. "
    "Stage Five C partnered with design engineering sales and support. "
    "Stage Five C improved onboarding outcomes and executive visibility. "
    "Stage Five C owned roadmap discovery delivery and launch readiness. "
    "Stage Five C documented customer feedback and coached product teams. "
    "Stage Five C used Product strategy Discovery Execution Communication. "
    "Stage Five C led product strategy for customer onboarding evidence 1. "
    "Stage Five C led product strategy for customer onboarding evidence 2. "
    "Stage Five C led product strategy for customer onboarding evidence 3. "
) * 3


def _evidence_payloads():
    return {
        "cards": [
            {
                "title": f"Evidence {index}",
                "problem": "Customer onboarding was unclear",
                "role": "Product lead",
                "action": "Led product strategy and cross-functional execution",
                "result": f"Improved onboarding outcomes with clear result {index}",
                "metric": None,
                "skills": ["Product strategy"],
                "competencies": ["Problem solving", "Communication"],
                "ownership_signal": "Owned roadmap delivery",
                "constraints": None,
                "tradeoffs": None,
                "missing_details": [],
                "source_excerpt": (
                    "Stage Five C led product strategy "
                    f"for customer onboarding evidence {index}."
                ),
                "source_location": "resume",
                "source_type": "resume",
                "source_highlight_id": None,
                "confidentiality_suggested": False,
                "duplicate_key": None,
                "duplicate_reason": None,
            }
            for index in range(1, 4)
        ]
    }


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_complete_mbp_workflow_from_signup_to_completed_sprint(client, django_user_model):
    signup_response = client.post(
        "/accounts/signup/",
        {
            "full_name": "Stage Five C",
            "email": "stage5c@example.com",
            "password1": "Str0ng-test-pass!",
            "password2": "Str0ng-test-pass!",
        },
    )
    assert signup_response.status_code in {302, 303}
    user = django_user_model.objects.get(username="stage5c@example.com")

    sprint = SprintWorkflowService.get_or_create_current_sprint(user)
    assert sprint.state == SprintState.DRAFT

    document = ResumeDocumentService.create_from_paste(user=user, text=RESUME_TEXT)
    assert document.parsing_status == DocumentParsingStatus.READY_FOR_REVIEW
    document = ResumeDocumentService.confirm_resume(
        user=user, sprint=sprint, document_id=document.id
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.RESUME_READY
    assert document.parsing_status == DocumentParsingStatus.CONFIRMED
    assert sprint.active_resume == document

    profile_client = MockAIClient()
    profile = CareerProfileService.ensure_draft_profile(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=profile_client)
    )
    profile = CareerProfileService.confirm_profile(
        user=user,
        sprint=sprint,
        profile_id=profile.id,
        cleaned_data={
            "full_name": "Stage Five C",
            "current_role": "Product Manager",
            "current_company": None,
            "years_experience": None,
            "industries": [],
            "functional_areas": ["Product management"],
            "skills": ["Product strategy", "Discovery"],
            "tools": [],
            "education_summary": None,
            "career_summary": "Led product strategy for customer onboarding.",
            "positioning_summary": "Product leader grounded in discovery and execution.",
        },
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED
    assert profile.confirmation_status == CareerProfileStatus.CONFIRMED
    assert sprint.active_profile == profile

    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(
            role_title="Senior Product Manager",
            target_seniority="Senior",
            company_name="ExampleCo",
            job_description=(
                "Lead product strategy, discovery, roadmap execution, and customer outcomes. " * 2
            ),
        ),
        ai_service=EvidraAIService(client=MockAIClient()),
    )
    opportunity = OpportunityService.skip_company_context(
        user=user, sprint=sprint, opportunity_id=opportunity.id
    )
    opportunity = OpportunityService.confirm_opportunity(
        user=user, sprint=sprint, opportunity_id=opportunity.id
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED
    assert opportunity.company_context_status == CompanyContextStatus.SKIPPED

    EvidenceService.extract_evidence(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=MockAIClient(responses=[_evidence_payloads()])),
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.EVIDENCE_REVIEW
    evidence = list(EvidenceCard.objects.filter(user=user, profile=profile).order_by("id"))
    assert len(evidence) == 3
    for card in evidence:
        EvidenceService.approve_card(user=user, sprint=sprint, card_id=card.id)
    threshold = EvidenceService.approve_evidence_set(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert threshold.is_met is True
    assert sprint.state == SprintState.EVIDENCE_APPROVED

    ai_service = EvidraAIService(client=MockAIClient())
    stories = StoryService.generate_stories(user=user, sprint=sprint, ai_service=ai_service)
    sprint.refresh_from_db()
    assert sprint.state == SprintState.STORIES_READY
    assert stories[0].status == StoryStatus.READY
    assert set(stories[0].evidence_ids).issubset({item.id for item in evidence})

    matches = MatchingService.generate_matches(user=user, sprint=sprint, ai_service=ai_service)
    sprint.refresh_from_db()
    selected = MatchingService.set_user_override(
        user=user, sprint=sprint, match_id=matches[0].id, story_id=stories[0].id
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.MATCHING_READY
    assert selected.user_selected is True
    assert selected.evidence_ids

    preview = ReadinessPreviewService.generate_preview(
        user=user, sprint=sprint, ai_service=ai_service
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREVIEW_READY
    assert preview.matched_story_excerpt["evidence_ids"]

    payment_service = RazorpayPaymentService(client=FakeRazorpayClient(order_id="order_stage5c"))
    payment = payment_service.create_or_reuse_order(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED
    assert sprint.state == SprintState.PAYMENT_PENDING

    body = webhook_body(order_id="order_stage5c", payment_id="pay_stage5c")
    result = payment_service.process_webhook(raw_body=body, signature=sign(body))
    sprint.refresh_from_db()
    payment.refresh_from_db()
    assert result.processed is True
    assert payment.status == PaymentStatus.PAID
    assert sprint.state == SprintState.PAID

    prepkit = PrepKitService.generate_prepkit(user=user, sprint=sprint, ai_service=ai_service)
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREPKIT_READY
    assert prepkit.question_bank[0]["source_refs"]

    question_id = PracticeService.priority_questions(user=user, sprint=sprint, prepkit=prepkit)[0][
        "question_id"
    ]
    attempt = PracticeService.submit_answer(
        user=user,
        sprint=sprint,
        question_id=question_id,
        answer_text=(
            "I led the approved product strategy work, explained the customer onboarding "
            "context, and connected my answer to the evidence-backed result clearly."
        ),
        ai_service=ai_service,
    )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PRACTICE_ACTIVE
    assert attempt.attempt_number == 1
    assert attempt.feedback["source_refs"]
    assert PracticeAttempt.objects.filter(sprint=sprint, question_id=question_id).count() == 1

    plan = ImprovementPlanService.generate_plan(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PLAN_READY
    assert plan.status == ImprovementPlanStatus.ACTIVE
    assert PlanTask.objects.filter(plan=plan).exists()

    completed_plan = ImprovementPlanService.complete_sprint(user=user, sprint=sprint)
    sprint.refresh_from_db()
    assert completed_plan.status == ImprovementPlanStatus.COMPLETED
    assert sprint.state == SprintState.COMPLETED
    assert sprint.completed_at is not None
