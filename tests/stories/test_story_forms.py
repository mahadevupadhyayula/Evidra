from apps.stories.forms import StoryEditForm


def valid_data(evidence_id="1"):
    return {
        "title": "Story",
        "story_type": "IMPACT",
        "situation": "Situation",
        "task": "Task",
        "action": "Action",
        "result": "Result",
        "learning": "Learning",
        "short_answer": "Short answer",
        "ninety_second_answer": "Ninety second answer",
        "detailed_answer": "Detailed answer",
        "competency_tags_text": "Execution, execution, Leadership",
        "seniority_signals_text": "Ownership",
        "missing_details_text": "",
        "evidence_ids": [evidence_id],
    }


def test_story_form_normalizes_lists_and_evidence_ids():
    form = StoryEditForm(data=valid_data(), approved_evidence_choices=[(1, "Evidence")])

    assert form.is_valid(), form.errors
    assert form.cleaned_data["competency_tags_text"] == ["Execution", "Leadership"]
    assert form.cleaned_data["evidence_ids"] == [1]


def test_story_form_rejects_unknown_evidence_choice():
    form = StoryEditForm(data=valid_data("99"), approved_evidence_choices=[(1, "Evidence")])

    assert not form.is_valid()
    assert "evidence_ids" in form.errors
