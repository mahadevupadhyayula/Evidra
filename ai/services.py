from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from ai.client import (
    AIClientError,
    CompanyContextExtractionClient,
    JDAnalysisClient,
    OpenAICompanyContextClient,
    OpenAIJDClient,
    OpenAIProfileClient,
    ProfileExtractionClient,
)
from ai.schemas.company_context import CompanyContext
from ai.schemas.jd import JDAnalysis
from ai.schemas.profile import ExtractedProfile


class AIProfileExtractionError(RuntimeError):
    """Raised when profile extraction cannot produce valid structured output."""


class AIJDAnalysisError(RuntimeError):
    """Raised when JD analysis cannot produce valid structured output."""


class AICompanyContextExtractionError(RuntimeError):
    """Raised when company context extraction cannot produce valid structured output."""


NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")


def ground_profile_in_resume(profile: ExtractedProfile, resume_text: str) -> ExtractedProfile:
    """Remove or reject profile fields that are not grounded in confirmed resume text."""

    normalized_resume = resume_text.casefold()
    updates: dict[str, object] = {}
    uncertain_fields = list(profile.uncertain_fields)

    for field_name in ["current_role", "current_company"]:
        value = getattr(profile, field_name)
        if value and value.casefold() not in normalized_resume:
            updates[field_name] = None
            if field_name not in uncertain_fields:
                uncertain_fields.append(field_name)

    for field_name in ["education_summary", "career_summary", "positioning_summary"]:
        value = getattr(profile, field_name)
        if value and _has_unsupported_numeric_claim(value, normalized_resume):
            updates[field_name] = None
            if field_name not in uncertain_fields:
                uncertain_fields.append(field_name)

    if updates or uncertain_fields != profile.uncertain_fields:
        updates["uncertain_fields"] = uncertain_fields
        return profile.model_copy(update=updates)
    return profile


def _has_unsupported_numeric_claim(value: str, normalized_resume: str) -> bool:
    for match in NUMERIC_CLAIM_PATTERN.finditer(value):
        if match.group(0).casefold() not in normalized_resume:
            return True
    return False


@dataclass(frozen=True)
class EvidraAIService:
    client: (
        ProfileExtractionClient | JDAnalysisClient | CompanyContextExtractionClient | None
    ) = None

    def extract_profile(self, confirmed_resume_text: str) -> ExtractedProfile:
        resume_text = confirmed_resume_text.strip()
        if not resume_text:
            raise AIProfileExtractionError("Confirmed resume text is required.")

        client = self.client or OpenAIProfileClient()
        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_profile = client.extract_profile(
                    resume_text=resume_text,
                    retry_context=retry_context,
                )
                profile = ExtractedProfile.model_validate(raw_profile)
                return ground_profile_in_resume(profile, resume_text)
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIProfileExtractionError(
            "Profile extraction returned invalid structured output."
        ) from last_error

    def extract_company_context(
        self,
        *,
        source_text: str,
        source_type: str,
        source_url: str | None = None,
    ) -> CompanyContext:
        context_text = source_text.strip()
        if not context_text:
            raise AICompanyContextExtractionError("Company context source text is required.")
        if source_type not in {"url", "paste"}:
            raise AICompanyContextExtractionError("Company context source type is invalid.")

        client = self.client or OpenAICompanyContextClient()
        if not hasattr(client, "extract_company_context"):
            raise AICompanyContextExtractionError("Company context client is not configured.")

        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_context = client.extract_company_context(
                    source_text=context_text,
                    source_type=source_type,
                    source_url=source_url,
                    retry_context=retry_context,
                )
                context = CompanyContext.model_validate(raw_context)
                return ground_company_context_in_source(context, context_text)
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AICompanyContextExtractionError(
            "Company context extraction returned invalid structured output."
        ) from last_error

    def analyze_jd(
        self,
        *,
        job_description: str,
        role_title: str,
        role_family: str,
        target_seniority: str,
        role_pack: dict,
    ) -> JDAnalysis:
        jd_text = job_description.strip()
        if not jd_text:
            raise AIJDAnalysisError("Job description is required.")

        client = self.client or OpenAIJDClient()
        if not hasattr(client, "analyze_jd"):
            raise AIJDAnalysisError("JD analysis client is not configured.")

        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_analysis = client.analyze_jd(
                    job_description=jd_text,
                    role_title=role_title.strip(),
                    role_family=role_family,
                    target_seniority=target_seniority.strip(),
                    role_pack=role_pack,
                    retry_context=retry_context,
                )
                analysis = JDAnalysis.model_validate(raw_analysis)
                return ground_jd_analysis_in_jd(analysis, jd_text)
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIJDAnalysisError("JD analysis returned invalid structured output.") from last_error


def ground_jd_analysis_in_jd(analysis: JDAnalysis, job_description: str) -> JDAnalysis:
    normalized_jd = job_description.casefold()
    return analysis.model_copy(
        update={
            "competencies": [
                item.model_copy(
                    update={
                        "source_excerpt": _valid_source_excerpt(item.source_excerpt, normalized_jd)
                    }
                )
                for item in analysis.competencies
            ],
            "skills": [
                item.model_copy(
                    update={
                        "source_excerpt": _valid_source_excerpt(item.source_excerpt, normalized_jd)
                    }
                )
                for item in analysis.skills
            ],
            "seniority_expectations": [
                item.model_copy(
                    update={
                        "source_excerpt": _valid_source_excerpt(item.source_excerpt, normalized_jd)
                    }
                )
                for item in analysis.seniority_expectations
            ],
            "likely_themes": [
                item.model_copy(
                    update={
                        "source_excerpt": _valid_source_excerpt(item.source_excerpt, normalized_jd)
                    }
                )
                for item in analysis.likely_themes
            ],
        }
    )


def _valid_source_excerpt(source_excerpt: str | None, normalized_jd: str) -> str | None:
    if not source_excerpt:
        return None
    if source_excerpt.casefold() in normalized_jd:
        return source_excerpt
    return None


def ground_company_context_in_source(context: CompanyContext, source_text: str) -> CompanyContext:
    normalized_source = _normalize_grounding_text(source_text)
    valid_references = [
        reference
        for reference in context.source_references
        if _normalize_grounding_text(reference.source_excerpt)
        and _normalize_grounding_text(reference.source_excerpt) in normalized_source
    ]
    referenced_fields = {reference.field for reference in valid_references}
    extracted_fields = {
        field_name
        for field_name in [
            "company_description",
            "products_or_services",
            "target_users",
            "business_model_clues",
            "product_terminology",
            "strategic_themes",
        ]
        if getattr(context, field_name)
    }
    unsupported_fields = extracted_fields - referenced_fields
    if unsupported_fields:
        raise ValueError("Company context fields must include valid source references.")
    unsupported_values = [
        field_name
        for field_name in extracted_fields
        if not _company_context_field_values_are_supported(
            getattr(context, field_name), normalized_source
        )
    ]
    if unsupported_values:
        raise ValueError("Company context values must appear in the provided source text.")
    return context.model_copy(update={"source_references": valid_references})


def _company_context_field_values_are_supported(value: object, normalized_source: str) -> bool:
    values = value if isinstance(value, list) else [value]
    return all(_normalize_grounding_text(item) in normalized_source for item in values if item)


def _normalize_grounding_text(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).split())
