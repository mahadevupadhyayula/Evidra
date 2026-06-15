from __future__ import annotations

from typing import Any

from django import forms

from apps.stories.models import Story


def parse_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    raw_items = value.replace("\n", ",").split(",") if isinstance(value, str) else value
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


class StoryEditForm(forms.ModelForm):
    competency_tags_text = forms.CharField(required=False, label="Competency tags")
    seniority_signals_text = forms.CharField(required=False, label="Seniority signals")
    missing_details_text = forms.CharField(
        required=False,
        label="Missing details",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    evidence_ids = forms.MultipleChoiceField(
        required=True,
        label="Approved evidence references",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Story
        fields = [
            "title",
            "story_type",
            "situation",
            "task",
            "action",
            "result",
            "learning",
            "short_answer",
            "ninety_second_answer",
            "detailed_answer",
        ]
        widgets = {
            "situation": forms.Textarea(attrs={"rows": 2}),
            "task": forms.Textarea(attrs={"rows": 2}),
            "action": forms.Textarea(attrs={"rows": 3}),
            "result": forms.Textarea(attrs={"rows": 2}),
            "learning": forms.Textarea(attrs={"rows": 2}),
            "short_answer": forms.Textarea(attrs={"rows": 3}),
            "ninety_second_answer": forms.Textarea(attrs={"rows": 5}),
            "detailed_answer": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, approved_evidence_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = approved_evidence_choices or []
        self.fields["evidence_ids"].choices = [(str(pk), label) for pk, label in choices]
        if self.instance and self.instance.pk:
            self.fields["competency_tags_text"].initial = list_to_text(
                self.instance.competency_tags
            )
            self.fields["seniority_signals_text"].initial = list_to_text(
                self.instance.seniority_signals
            )
            self.fields["missing_details_text"].initial = list_to_text(
                self.instance.missing_details
            )
            self.fields["evidence_ids"].initial = [str(item) for item in self.instance.evidence_ids]

    def clean_title(self) -> str:
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Stories need a title.")
        return title

    def clean_story_type(self) -> str:
        return (self.cleaned_data.get("story_type") or "").strip()

    def clean_short_answer(self) -> str:
        return self._clean_answer("short_answer", 1200)

    def clean_ninety_second_answer(self) -> str:
        return self._clean_answer("ninety_second_answer", 3000)

    def clean_detailed_answer(self) -> str:
        return self._clean_answer("detailed_answer", 6000)

    def clean_competency_tags_text(self) -> list[str]:
        values = parse_list(self.cleaned_data.get("competency_tags_text"))
        if len(values) > 12:
            raise forms.ValidationError("Use at most 12 competency tags.")
        return values

    def clean_seniority_signals_text(self) -> list[str]:
        values = parse_list(self.cleaned_data.get("seniority_signals_text"))
        if len(values) > 8:
            raise forms.ValidationError("Use at most 8 seniority signals.")
        return values

    def clean_missing_details_text(self) -> list[str]:
        values = parse_list(self.cleaned_data.get("missing_details_text"))
        if len(values) > 10:
            raise forms.ValidationError("Use at most 10 missing-detail prompts.")
        return values

    def clean_evidence_ids(self) -> list[int]:
        raw_ids = self.cleaned_data.get("evidence_ids") or []
        ids = [int(item) for item in raw_ids]
        if not ids:
            raise forms.ValidationError("Select at least one approved evidence reference.")
        return ids

    def _clean_answer(self, field_name: str, max_length: int) -> str:
        value = (self.cleaned_data.get(field_name) or "").strip()
        if not value:
            raise forms.ValidationError("This answer is required.")
        if len(value) > max_length:
            raise forms.ValidationError(f"Keep this answer under {max_length} characters.")
        return value
