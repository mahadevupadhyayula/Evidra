from django import forms


class PracticeAnswerForm(forms.Form):
    question_id = forms.ChoiceField()
    answer_text = forms.CharField(
        min_length=20,
        max_length=6000,
        widget=forms.Textarea(attrs={"rows": 8}),
    )

    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = questions or []
        self.fields["question_id"].choices = [
            (question["question_id"], question["question"]) for question in self.questions
        ]

    def clean_question_id(self):
        question_id = self.cleaned_data["question_id"]
        valid_ids = {question["question_id"] for question in self.questions}
        if question_id not in valid_ids:
            raise forms.ValidationError("Choose a current practice question.")
        return question_id
