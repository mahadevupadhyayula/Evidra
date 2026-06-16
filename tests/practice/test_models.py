import pytest
from django.db import IntegrityError

from apps.practice.models import PracticeAttempt
from tests.practice.helpers import make_practice_ready_sprint


@pytest.mark.django_db
def test_practice_attempt_is_append_only_record_with_unique_question_attempt_number():
    _user, sprint, _prepkit = make_practice_ready_sprint()
    PracticeAttempt.objects.create(
        sprint=sprint,
        question_id="q1",
        answer_text="This is a sufficiently long answer.",
        relevance_score=4,
        structure_score=4,
        specificity_score=4,
        ownership_score=4,
        impact_score=4,
        clarity_score=4,
        improved_answer="Improved answer",
        follow_up_question="What next?",
        attempt_number=1,
    )

    with pytest.raises(IntegrityError):
        PracticeAttempt.objects.create(
            sprint=sprint,
            question_id="q1",
            answer_text="This is a sufficiently long answer again.",
            relevance_score=4,
            structure_score=4,
            specificity_score=4,
            ownership_score=4,
            impact_score=4,
            clarity_score=4,
            improved_answer="Improved answer",
            follow_up_question="What next?",
            attempt_number=1,
        )
