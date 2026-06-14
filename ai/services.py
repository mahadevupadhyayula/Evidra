from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from ai.client import (
    AIClientError,
    JDAnalysisClient,
    OpenAIJDClient,
    OpenAIProfileClient,
    ProfileExtractionClient,
)
from ai.schemas.jd import JDAnalysis
from ai.schemas.profile import ExtractedProfile


class AIProfileExtractionError(RuntimeError):
    """Raised when profile extraction cannot produce valid structured output."""


class AIJDAnalysisError(RuntimeError):
    """Raised when JD analysis cannot produce valid structured output."""


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
    client: ProfileExtractionClient | JDAnalysisClient | None = None

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
