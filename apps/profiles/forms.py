from __future__ import annotations

from django import forms

from ai.schemas.profile import contains_sensitive_inference, normalize_text_list
from apps.profiles.models import CareerProfile


class CareerProfileForm(forms.ModelForm):
    industries = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    functional_areas = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    skills = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    tools = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    class Meta:
        model = CareerProfile
        fields = [
            "full_name",
            "current_role",
            "current_company",
            "years_experience",
            "industries",
            "functional_areas",
            "skills",
            "tools",
            "education_summary",
            "career_summary",
            "positioning_summary",
        ]
        widgets = {
            "education_summary": forms.Textarea(attrs={"rows": 4}),
            "career_summary": forms.Textarea(attrs={"rows": 5}),
            "positioning_summary": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        initial = kwargs.setdefault("initial", {})
        if instance is not None:
            for field_name in ["industries", "functional_areas", "skills", "tools"]:
                initial.setdefault(field_name, "\n".join(getattr(instance, field_name) or []))
        super().__init__(*args, **kwargs)
        self.fields["years_experience"].required = False
        self.fields["years_experience"].min_value = 0
        self.fields["years_experience"].max_value = 80

    def clean(self):
        cleaned_data = super().clean()
        for field_name in [
            "full_name",
            "current_role",
            "current_company",
            "education_summary",
            "career_summary",
            "positioning_summary",
        ]:
            value = cleaned_data.get(field_name)
            if isinstance(value, str):
                value = value.strip()
                cleaned_data[field_name] = value or None
            if value and contains_sensitive_inference(value):
                self.add_error(field_name, "Remove sensitive or demographic information.")
        return cleaned_data

    def clean_years_experience(self) -> int | None:
        years = self.cleaned_data.get("years_experience")
        if years is not None and years > 80:
            raise forms.ValidationError("Years of experience must be 80 or less.")
        return years

    def clean_industries(self) -> list[str]:
        return self._clean_list_field("industries")

    def clean_functional_areas(self) -> list[str]:
        return self._clean_list_field("functional_areas")

    def clean_skills(self) -> list[str]:
        return self._clean_list_field("skills")

    def clean_tools(self) -> list[str]:
        return self._clean_list_field("tools")

    def _clean_list_field(self, field_name: str) -> list[str]:
        values = normalize_text_list(self.cleaned_data.get(field_name))
        for value in values:
            if contains_sensitive_inference(value):
                raise forms.ValidationError("Remove sensitive or demographic information.")
        return values
