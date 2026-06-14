from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings
from openai import OpenAI

from ai.schemas.company_context import CompanyContext
from ai.schemas.jd import JDAnalysis
from ai.schemas.profile import ExtractedProfile


class AIClientError(RuntimeError):
    """Raised when an AI client cannot return structured data."""


class ProfileExtractionClient(Protocol):
    def extract_profile(self, *, resume_text: str, retry_context: str | None = None) -> dict:
        """Return raw profile data for schema validation."""


class CompanyContextExtractionClient(Protocol):
    def extract_company_context(
        self,
        *,
        source_text: str,
        source_type: str,
        source_url: str | None = None,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw company context data for schema validation."""


class JDAnalysisClient(Protocol):
    def analyze_jd(
        self,
        *,
        job_description: str,
        role_title: str,
        role_family: str,
        target_seniority: str,
        role_pack: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw JD analysis data for schema validation."""


@dataclass
class MockAIClient:
    responses: list[dict | Exception] = field(default_factory=list)
    calls: list[dict[str, object]] = field(default_factory=list)

    def extract_profile(self, *, resume_text: str, retry_context: str | None = None) -> dict:
        self.calls.append({"resume_text": resume_text, "retry_context": retry_context})
        if not self.responses:
            return {
                "full_name": None,
                "current_role": None,
                "current_company": None,
                "years_experience": None,
                "industries": [],
                "functional_areas": [],
                "skills": [],
                "tools": [],
                "education_summary": None,
                "career_summary": None,
                "positioning_summary": None,
                "uncertain_fields": [],
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def extract_company_context(
        self,
        *,
        source_text: str,
        source_type: str,
        source_url: str | None = None,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "extract_company_context",
                "source_text": source_text,
                "source_type": source_type,
                "source_url": source_url,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            return {
                "source_type": source_type,
                "source_url": source_url,
                "company_description": source_text[:80] or "company",
                "products_or_services": [],
                "target_users": [],
                "business_model_clues": [],
                "product_terminology": [],
                "strategic_themes": [],
                "source_references": [
                    {
                        "field": "company_description",
                        "source_excerpt": source_text[:80] or "company",
                    }
                ],
                "uncertain_fields": [],
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def analyze_jd(
        self,
        *,
        job_description: str,
        role_title: str,
        role_family: str,
        target_seniority: str,
        role_pack: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "analyze_jd",
                "job_description": job_description,
                "role_title": role_title,
                "role_family": role_family,
                "target_seniority": target_seniority,
                "role_pack": role_pack,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            return {
                "summary": (
                    "The role emphasizes solving customer problems and collaborating across teams."
                ),
                "competencies": [
                    {"name": "Problem solving", "description": None, "source_excerpt": None}
                ],
                "skills": [
                    {"name": "Communication", "category": "communication", "source_excerpt": None}
                ],
                "seniority_expectations": [
                    {
                        "expectation": "Own outcomes with appropriate guidance.",
                        "source_excerpt": None,
                    }
                ],
                "likely_themes": [
                    {"theme": "Cross-functional collaboration", "source_excerpt": None}
                ],
                "uncertain_fields": [],
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OpenAIProfileClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.EVIDRA_OPENAI_MODEL
        if not self.api_key:
            raise AIClientError("OpenAI API key is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def extract_profile(self, *, resume_text: str, retry_context: str | None = None) -> dict:
        prompt = (
            "Extract a career profile from the confirmed resume text only. "
            "Do not infer demographic or sensitive attributes. Use null for unknowns. "
            "Return JSON with the required profile schema."
        )
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extracted_profile",
                        "schema": ExtractedProfile.model_json_schema(),
                        "strict": True,
                    },
                },
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": resume_text},
                ],
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise AIClientError("Profile extraction failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Profile extraction returned invalid JSON.")
        return parsed


class OpenAIJDClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.EVIDRA_OPENAI_MODEL
        if not self.api_key:
            raise AIClientError("OpenAI API key is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def analyze_jd(
        self,
        *,
        job_description: str,
        role_title: str,
        role_family: str,
        target_seniority: str,
        role_pack: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.jd import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "role_title": role_title,
            "role_family": role_family,
            "target_seniority": target_seniority,
            "role_pack": role_pack,
            "job_description": job_description,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "jd_analysis",
                        "schema": JDAnalysis.model_json_schema(),
                        "strict": True,
                    },
                },
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise AIClientError("JD analysis failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("JD analysis returned invalid JSON.")
        return parsed


class OpenAICompanyContextClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.EVIDRA_OPENAI_MODEL
        if not self.api_key:
            raise AIClientError("OpenAI API key is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def extract_company_context(
        self,
        *,
        source_text: str,
        source_type: str,
        source_url: str | None = None,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.company_context import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "source_type": source_type,
            "source_url": source_url,
            "source_text": source_text,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "company_context",
                        "schema": CompanyContext.model_json_schema(),
                        "strict": True,
                    },
                },
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise AIClientError("Company context extraction failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Company context extraction returned invalid JSON.")
        return parsed
