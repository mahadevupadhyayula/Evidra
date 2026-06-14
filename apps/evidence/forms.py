from __future__ import annotations

from typing import Any

from django import forms

from apps.evidence.models import CareerHighlight, EvidenceCard


def parse_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    else:
        raw_items = value
    items: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            items.append(text)
    return items


def list_to_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value if str(item).strip())


class CareerHighlightForm(forms.ModelForm):
    skills_text = forms.CharField(
        required=False,
        label="Skills",
        help_text="Separate skills with commas.",
        widget=forms.TextInput,
    )

    class Meta:
        model = CareerHighlight
        fields = ["title", "description", "metric", "source_note"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "source_note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["skills_text"].initial = list_to_text(self.instance.skills)

    def clean_title(self) -> str:
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Add a short title for this highlight.")
        return title

    def clean_description(self) -> str:
        description = self.cleaned_data["description"].strip()
        if len(description) < 20:
            raise forms.ValidationError("Add at least 20 characters of detail.")
        return description

    def clean_metric(self) -> str | None:
        metric = self.cleaned_data.get("metric") or ""
        return metric.strip() or None

    def clean_source_note(self) -> str:
        return (self.cleaned_data.get("source_note") or "").strip()

    def clean_skills_text(self) -> list[str]:
        return parse_list(self.cleaned_data.get("skills_text"))


class EvidenceCardForm(forms.ModelForm):
    skills_text = forms.CharField(required=False, label="Skills")
    competencies_text = forms.CharField(required=False, label="Competencies")
    metric_user_corrected = forms.BooleanField(
        required=False,
        label="I confirm this metric is accurate even though it is not in the source excerpt.",
    )
    missing_details_text = forms.CharField(
        required=False,
        label="Missing-detail prompts",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = EvidenceCard
        fields = [
            "title",
            "problem",
            "role",
            "action",
            "result",
            "metric",
            "ownership_signal",
            "constraints",
            "tradeoffs",
            "source_excerpt",
            "source_location",
            "confidentiality",
        ]
        widgets = {
            "problem": forms.Textarea(attrs={"rows": 2}),
            "role": forms.Textarea(attrs={"rows": 2}),
            "action": forms.Textarea(attrs={"rows": 3}),
            "result": forms.Textarea(attrs={"rows": 2}),
            "ownership_signal": forms.Textarea(attrs={"rows": 2}),
            "constraints": forms.Textarea(attrs={"rows": 2}),
            "tradeoffs": forms.Textarea(attrs={"rows": 2}),
            "source_excerpt": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["skills_text"].initial = list_to_text(self.instance.skills)
            self.fields["competencies_text"].initial = list_to_text(self.instance.competencies)
            self.fields["missing_details_text"].initial = list_to_text(
                self.instance.missing_details
            )
            self.fields["metric_user_corrected"].initial = bool(
                self.instance.user_edited_data.get("metric_user_corrected")
            )

    def clean_title(self) -> str:
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Evidence cards need a title.")
        return title

    def clean_source_excerpt(self) -> str:
        excerpt = self.cleaned_data["source_excerpt"].strip()
        if not excerpt:
            raise forms.ValidationError("Evidence cards need a source excerpt.")
        return excerpt

    def clean_metric(self) -> str | None:
        metric = self.cleaned_data.get("metric") or ""
        return metric.strip() or None

    def clean_source_location(self) -> str:
        return (self.cleaned_data.get("source_location") or "").strip()

    def clean_skills_text(self) -> list[str]:
        return parse_list(self.cleaned_data.get("skills_text"))

    def clean_competencies_text(self) -> list[str]:
        return parse_list(self.cleaned_data.get("competencies_text"))

    def clean_missing_details_text(self) -> list[str]:
        return parse_list(self.cleaned_data.get("missing_details_text"))
