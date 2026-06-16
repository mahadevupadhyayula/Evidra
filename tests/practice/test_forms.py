from apps.practice.forms import PracticeAnswerForm

QUESTIONS = [{"question_id": "q1", "question": "Tell me about the approved story."}]


def test_practice_answer_form_accepts_valid_text_answer():
    form = PracticeAnswerForm(
        {"question_id": "q1", "answer_text": "This is a sufficiently detailed answer."},
        questions=QUESTIONS,
    )

    assert form.is_valid()


def test_practice_answer_form_rejects_unknown_question():
    form = PracticeAnswerForm(
        {"question_id": "other", "answer_text": "This is a sufficiently detailed answer."},
        questions=QUESTIONS,
    )

    assert not form.is_valid()
    assert "question_id" in form.errors


def test_practice_answer_form_rejects_short_answer():
    form = PracticeAnswerForm(
        {"question_id": "q1", "answer_text": "Too short"}, questions=QUESTIONS
    )

    assert not form.is_valid()
    assert "answer_text" in form.errors
