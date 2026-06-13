from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings
from openai import OpenAI

from ai.schemas.profile import ExtractedProfile


class AIClientError(RuntimeError):
    """Raised when an AI client cannot return profile data."""


class ProfileExtractionClient(Protocol):
    def extract_profile(self, *, resume_text: str, retry_context: str | None = None) -> dict:
        """Return raw profile data for schema validation."""


@dataclass
class MockAIClient:
    responses: list[dict | Exception] = field(default_factory=list)
    calls: list[dict[str, str | None]] = field(default_factory=list)

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
