from django import forms

from ai.schemas.company_context import CompanyContext
from apps.opportunities.models import Opportunity, RoleFamily
from apps.opportunities.role_packs import RolePackError, get_role_pack

MIN_JOB_DESCRIPTION_LENGTH = 100
MAX_JOB_DESCRIPTION_LENGTH = 50_000
MAX_LONG_CONTEXT_LENGTH = 5_000
MAX_PASTED_COMPANY_CONTEXT_LENGTH = 15_000


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
        for field_name in [
            "role_title",
            "target_seniority",
            "company_name",
            "interview_stage",
        ]:
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


class CompanyContextForm(forms.Form):
    company_url = forms.URLField(
        required=False,
        max_length=2048,
        assume_scheme="https",
        help_text="Optional. We fetch at most this one public page.",
    )
    pasted_company_context = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text=(
            "Optional fallback. Paste company or product context if you prefer not "
            "to fetch a page."
        ),
    )

    def clean_company_url(self) -> str:
        company_url = (self.cleaned_data.get("company_url") or "").strip()
        if company_url and not company_url.startswith(("http://", "https://")):
            raise forms.ValidationError("Enter a public http or https URL.")
        return company_url

    def clean_pasted_company_context(self) -> str:
        context = (self.cleaned_data.get("pasted_company_context") or "").strip()
        if len(context) > MAX_PASTED_COMPANY_CONTEXT_LENGTH:
            raise forms.ValidationError("Keep pasted company context under 15,000 characters.")
        return context

    def clean(self):
        cleaned_data = super().clean()
        company_url = cleaned_data.get("company_url") or ""
        pasted = cleaned_data.get("pasted_company_context") or ""
        if company_url and pasted:
            raise forms.ValidationError("Provide either a URL or pasted company context, not both.")
        if not company_url and not pasted:
            raise forms.ValidationError(
                "Provide a URL, paste company context, or use continue without company context."
            )
        return cleaned_data


class CompanyContextReviewForm(forms.Form):
    company_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Review or correct the short company/product description.",
    )
    products_or_services = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One product or service per line.",
    )
    target_users = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One target user or customer segment per line.",
    )
    business_model_clues = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One business-model clue per line.",
    )
    product_terminology = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One product/company term per line.",
    )
    strategic_themes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One strategic theme per line.",
    )

    @classmethod
    def from_company_context(cls, company_context: dict | None):
        context = company_context or {}
        return cls(
            initial={
                "company_description": context.get("company_description") or "",
                "products_or_services": "\n".join(context.get("products_or_services") or []),
                "target_users": "\n".join(context.get("target_users") or []),
                "business_model_clues": "\n".join(context.get("business_model_clues") or []),
                "product_terminology": "\n".join(context.get("product_terminology") or []),
                "strategic_themes": "\n".join(context.get("strategic_themes") or []),
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        payload = self.to_company_context_payload(cleaned_data)
        try:
            CompanyContext.model_validate(payload)
        except ValueError as exc:
            raise forms.ValidationError(
                "Reviewed company context must include useful text."
            ) from exc
        cleaned_data["company_context_payload"] = payload
        return cleaned_data

    @staticmethod
    def to_company_context_payload(cleaned_data: dict) -> dict:
        return {
            "source_type": "paste",
            "source_url": None,
            "company_description": (cleaned_data.get("company_description") or "").strip()
            or None,
            "products_or_services": _split_review_lines(
                cleaned_data.get("products_or_services") or ""
            ),
            "target_users": _split_review_lines(cleaned_data.get("target_users") or ""),
            "business_model_clues": _split_review_lines(
                cleaned_data.get("business_model_clues") or ""
            ),
            "product_terminology": _split_review_lines(
                cleaned_data.get("product_terminology") or ""
            ),
            "strategic_themes": _split_review_lines(cleaned_data.get("strategic_themes") or ""),
            "source_references": [],
            "uncertain_fields": [],
        }


def _split_review_lines(value: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_line in value.replace(",", "\n").splitlines():
        item = raw_line.strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            values.append(item)
    return values
