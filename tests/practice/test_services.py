import pytest
from django.contrib.auth import get_user_model

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.practice.models import PracticeAttempt
from apps.practice.services import PracticeError, PracticeService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from tests.practice.helpers import make_practice_ready_sprint


@pytest.mark.django_db
def test_priority_questions_sort_high_priority_first():
    user, sprint, prepkit = make_practice_ready_sprint()
    prepkit.question_bank = [
        {"question": "Low question", "priority": "low"},
        {"question": "High question", "priority": "high"},
    ]
    prepkit.save(update_fields=["question_bank", "updated_at"])

    questions = PracticeService.priority_questions(user=user, sprint=sprint, prepkit=prepkit)

    assert [question["question"] for question in questions] == ["High question", "Low question"]


@pytest.mark.django_db
def test_submit_answer_creates_attempt_and_transitions_to_practice_active():
    user, sprint, _prepkit = make_practice_ready_sprint()

    attempt = PracticeService.submit_answer(
        user=user,
        sprint=sprint,
        question_id="q1",
        answer_text="I led the approved work and explained the result clearly.",
        ai_service=EvidraAIService(client=MockAIClient()),
    )

    sprint.refresh_from_db()
    assert attempt.attempt_number == 1
    assert attempt.linked_story is not None
    assert attempt.feedback["strengths"]
    assert attempt.feedback["unsupported_claims"] == []
    assert sprint.state == SprintState.PRACTICE_ACTIVE


@pytest.mark.django_db
def test_submit_answer_appends_attempts_and_computes_comparison():
    user, sprint, _prepkit = make_practice_ready_sprint()
    service = EvidraAIService(client=MockAIClient())

    first = PracticeService.submit_answer(
        user=user,
        sprint=sprint,
        question_id="q1",
        answer_text="I led the approved work and explained the result clearly.",
        ai_service=service,
    )
    sprint.refresh_from_db()
    second = PracticeService.submit_answer(
        user=user,
        sprint=sprint,
        question_id="q1",
        answer_text="I led the approved work and explained the result clearly again.",
        ai_service=service,
    )

    assert first.attempt_number == 1
    assert second.attempt_number == 2
    assert second.feedback["comparison"]["previous_attempt_id"] == first.id
    assert PracticeAttempt.objects.filter(sprint=sprint, question_id="q1").count() == 2


@pytest.mark.django_db
def test_submit_answer_rejects_cross_user_sprint():
    _user, sprint, _prepkit = make_practice_ready_sprint()
    other = get_user_model().objects.create_user(username="practice-other@example.com")

    with pytest.raises(SprintOwnershipError):
        PracticeService.submit_answer(
            user=other,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_submit_answer_requires_prepkit_ready_state():
    user, sprint, _prepkit = make_practice_ready_sprint()
    sprint.state = SprintState.PAID
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(InvalidSprintTransition):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_submit_answer_rejects_unknown_question():
    user, sprint, _prepkit = make_practice_ready_sprint()

    with pytest.raises(PracticeError, match="current practice question"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="unknown",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_numeric_claim_in_improved_answer():
    user, sprint, _prepkit = make_practice_ready_sprint()
    client = MockAIClient(
        responses=[
            {
                "relevance_score": 4,
                "structure_score": 4,
                "specificity_score": 4,
                "ownership_score": 4,
                "impact_score": 4,
                "clarity_score": 4,
                "strengths": ["Grounded"],
                "improvements": ["Add detail"],
                "improved_answer": "I increased revenue by 999%.",
                "follow_up_question": "What did you learn?",
                "unsupported_claims": [],
                "source_refs": [],
            },
            {
                "relevance_score": 4,
                "structure_score": 4,
                "specificity_score": 4,
                "ownership_score": 4,
                "impact_score": 4,
                "clarity_score": 4,
                "strengths": ["Grounded"],
                "improvements": ["Add detail"],
                "improved_answer": "I increased revenue by 999%.",
                "follow_up_question": "What did you learn?",
                "unsupported_claims": [],
                "source_refs": [],
            },
        ]
    )

    with pytest.raises(PracticeError, match="invalid structured output"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=client),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_named_claim_in_improved_answer():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add detail"],
        "improved_answer": "I led Acme Corp launch successfully.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(PracticeError, match="unsupported named claim"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unresolved_recommended_story():
    user, sprint, prepkit = make_practice_ready_sprint()
    prepkit.question_bank[0]["recommended_story_id"] = 999999
    prepkit.save(update_fields=["question_bank", "updated_at"])

    with pytest.raises(PracticeError, match="linked story"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient()),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_lowercase_factual_terms():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add detail"],
        "improved_answer": "I built a fraud detection platform.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(PracticeError, match="unsupported factual term"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unresolved_referenced_evidence():
    user, sprint, prepkit = make_practice_ready_sprint()
    prepkit.question_bank[0]["evidence_ids"] = [999999]
    prepkit.question_bank[0]["recommended_story_id"] = None
    prepkit.save(update_fields=["question_bank", "updated_at"])

    with pytest.raises(PracticeError, match="Referenced evidence"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient()),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_mark_practice_active_rejects_attempt_from_other_sprint():
    user, sprint, _prepkit = make_practice_ready_sprint("transition-owner@example.com")
    other_user, other_sprint, _other_prepkit = make_practice_ready_sprint(
        "transition-other@example.com"
    )
    attempt = PracticeService.submit_answer(
        user=other_user,
        sprint=other_sprint,
        question_id="q1",
        answer_text="I led the approved work and explained the result clearly.",
        ai_service=EvidraAIService(client=MockAIClient()),
    )

    with pytest.raises(SprintOwnershipError):
        SprintWorkflowService.mark_practice_active(user=user, sprint=sprint, attempt=attempt)


@pytest.mark.django_db
def test_mark_practice_active_rejects_unsaved_attempt():
    user, sprint, _prepkit = make_practice_ready_sprint("unsaved-transition@example.com")
    unsaved = PracticeAttempt(
        sprint=sprint,
        question_id="q1",
        answer_text="I led the approved work and explained the result clearly.",
        relevance_score=4,
        structure_score=4,
        specificity_score=4,
        ownership_score=4,
        impact_score=4,
        clarity_score=4,
        improved_answer="I led the approved work.",
        follow_up_question="What did you learn?",
        attempt_number=1,
    )

    with pytest.raises(SprintTransitionConditionMissing, match="persisted practice attempt"):
        SprintWorkflowService.mark_practice_active(user=user, sprint=sprint, attempt=unsaved)


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_named_claim_in_strength():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Strong Acme Corp detail"],
        "improvements": ["Add detail"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(PracticeError, match="Strength contains an unsupported named claim"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_factual_claim_in_improvement():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add platform migration detail"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(PracticeError, match="Improvement contains an unsupported factual term"):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_factual_claim_in_follow_up_question():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add detail"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "How did the migration platform change churn?",
        "unsupported_claims": [],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(
        PracticeError, match="Follow-up question contains an unsupported factual term"
    ):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0


@pytest.mark.django_db
def test_submit_answer_rejects_unsupported_claim_not_present_in_answer():
    user, sprint, _prepkit = make_practice_ready_sprint()
    response = {
        "relevance_score": 4,
        "structure_score": 4,
        "specificity_score": 4,
        "ownership_score": 4,
        "impact_score": 4,
        "clarity_score": 4,
        "strengths": ["Grounded"],
        "improvements": ["Add detail"],
        "improved_answer": "I led the approved work.",
        "follow_up_question": "What did you learn?",
        "unsupported_claims": [
            {
                "claim": "Launched an AI platform",
                "reason": "This claim is unsupported.",
                "suggested_fix": "Use approved work detail.",
            }
        ],
        "source_refs": [{"source_type": "question", "source_id": "q1"}],
    }

    with pytest.raises(
        PracticeError, match="Unsupported claim contains an unsupported factual term"
    ):
        PracticeService.submit_answer(
            user=user,
            sprint=sprint,
            question_id="q1",
            answer_text="I led the approved work and explained the result clearly.",
            ai_service=EvidraAIService(client=MockAIClient(responses=[response])),
        )
    assert PracticeAttempt.objects.filter(sprint=sprint).count() == 0
