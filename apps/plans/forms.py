from django import forms

from apps.plans.models import PlanTaskStatus


class PlanGenerateForm(forms.Form):
    force = forms.BooleanField(required=False)


class PlanTaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=PlanTaskStatus.choices)


class SprintCompleteForm(forms.Form):
    confirm = forms.BooleanField(required=True)
