from django import forms

from apps.opportunities.models import Opportunity, RoleFamily
from apps.opportunities.role_packs import RolePackError, get_role_pack

MIN_JOB_DESCRIPTION_LENGTH = 100
MAX_JOB_DESCRIPTION_LENGTH = 50_000
MAX_LONG_CONTEXT_LENGTH = 5_000


class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = [
            "role_title",
            "role_family",
            "target_seniority",
            "company_name",
            "job_description",
            "interview_stage",
            "interview_date",
            "concerns",
            "improvement_goals",
        ]
        widgets = {
            "job_description": forms.Textarea(attrs={"rows": 16}),
            "interview_date": forms.DateInput(attrs={"type": "date"}),
            "concerns": forms.Textarea(attrs={"rows": 4}),
            "improvement_goals": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role_family"].choices = RoleFamily.choices
        for field_name in ["role_title", "role_family", "target_seniority", "company_name"]:
            self.fields[field_name].required = True
        for field_name in ["interview_stage", "interview_date", "concerns", "improvement_goals"]:
            self.fields[field_name].required = False

    def clean_role_family(self) -> str:
        role_family = self.cleaned_data["role_family"]
        try:
            RoleFamily(role_family)
            get_role_pack(role_family)
        except (ValueError, RolePackError) as exc:
            raise forms.ValidationError("Choose a supported role family.") from exc
        return role_family

    def clean_job_description(self) -> str:
        job_description = self.cleaned_data["job_description"].strip()
        if len(job_description) < MIN_JOB_DESCRIPTION_LENGTH:
            raise forms.ValidationError("Paste at least 100 characters from the job description.")
        if len(job_description) > MAX_JOB_DESCRIPTION_LENGTH:
            raise forms.ValidationError("Job description is too long.")
        return job_description

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ["role_title", "target_seniority", "company_name", "interview_stage"]:
            value = cleaned_data.get(field_name)
            if isinstance(value, str):
                cleaned_data[field_name] = value.strip()
        for field_name in ["concerns", "improvement_goals"]:
            value = cleaned_data.get(field_name) or ""
            value = value.strip()
            if len(value) > MAX_LONG_CONTEXT_LENGTH:
                self.add_error(field_name, "Keep this response under 5,000 characters.")
            cleaned_data[field_name] = value
        return cleaned_data
