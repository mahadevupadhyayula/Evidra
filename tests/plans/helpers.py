from apps.practice.models import PracticeAttempt
from apps.sprints.services import SprintWorkflowService
from tests.practice.helpers import make_practice_ready_sprint


def make_plan_ready_inputs(username="plan@example.com"):
    user, sprint, prepkit = make_practice_ready_sprint(username)
    question = prepkit.question_bank[0]
    attempt = PracticeAttempt.objects.create(
        sprint=sprint,
        question_id=question.get("id", "q1"),
        answer_text="I worked through the customer problem and explained the impact clearly.",
        relevance_score=2,
        structure_score=3,
        specificity_score=2,
        ownership_score=3,
        impact_score=2,
        clarity_score=3,
        feedback={
            "improvements": ["Add a clearer result."],
            "unsupported_claims": [{"claim": "42% growth", "reason": "Not approved."}],
        },
        improved_answer="A more grounded answer uses approved evidence only.",
        follow_up_question="What would you do differently?",
        attempt_number=1,
    )
    SprintWorkflowService.mark_practice_active(user=user, sprint=sprint, attempt=attempt)
    sprint.refresh_from_db()
    return user, sprint, prepkit, attempt
