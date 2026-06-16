from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings
from openai import OpenAI

from ai.schemas.company_context import CompanyContext
from ai.schemas.evidence import ExtractedEvidenceSet
from ai.schemas.jd import JDAnalysis
from ai.schemas.matching import StoryMatchSet
from ai.schemas.practice import PracticeFeedbackOutput
from ai.schemas.prepkit import PrepKitAnalysisOutput, PrepKitArtifactOutput
from ai.schemas.preview import ReadinessPreviewOutput
from ai.schemas.profile import ExtractedProfile
from ai.schemas.stories import GeneratedStorySet, StoryScoreSet


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


class EvidenceExtractionClient(Protocol):
    def extract_evidence(
        self,
        *,
        resume_text: str,
        highlights: list[dict],
        profile_context: dict,
        opportunity_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw evidence data for schema validation."""


class StoryGenerationClient(Protocol):
    def generate_stories(
        self,
        *,
        approved_evidence: list[dict],
        profile_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw reusable story data for schema validation."""


class StoryScoringClient(Protocol):
    def score_stories(
        self,
        *,
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        """Return raw story score data for schema validation."""


class StoryMatchScoringClient(Protocol):
    def score_story_matches(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        competency_map: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        """Return raw story-match component scores for schema validation."""


class PreviewGenerationClient(Protocol):
    def generate_preview(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        matched_story_excerpt_source: dict,
        deterministic_counts: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw readiness preview data for schema validation."""


class PrepKitAnalysisClient(Protocol):
    def generate_prepkit_analysis(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw Prep Kit analysis data for schema validation."""


class PrepKitArtifactClient(Protocol):
    def generate_prepkit_artifact(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        analysis: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw Prep Kit artifact data for schema validation."""


class AnswerEvaluationClient(Protocol):
    def evaluate_answer(
        self,
        *,
        question: dict,
        answer_text: str,
        linked_story: dict | None,
        approved_evidence: list[dict],
        prepkit_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        """Return raw practice-answer feedback for schema validation."""


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

    def extract_evidence(
        self,
        *,
        resume_text: str,
        highlights: list[dict],
        profile_context: dict,
        opportunity_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "extract_evidence",
                "resume_text": resume_text,
                "highlights": highlights,
                "profile_context": profile_context,
                "opportunity_context": opportunity_context,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            excerpt = resume_text[:80] or "Resume evidence"
            return {
                "cards": [
                    {
                        "title": "Evidence from resume",
                        "problem": None,
                        "role": None,
                        "action": excerpt,
                        "result": None,
                        "metric": None,
                        "skills": [],
                        "competencies": [],
                        "ownership_signal": None,
                        "constraints": None,
                        "tradeoffs": None,
                        "missing_details": ["Add the measurable result."],
                        "source_excerpt": excerpt,
                        "source_location": "resume",
                        "source_type": "resume",
                        "source_highlight_id": None,
                        "confidentiality_suggested": False,
                        "duplicate_key": None,
                        "duplicate_reason": None,
                    }
                ]
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_stories(
        self,
        *,
        approved_evidence: list[dict],
        profile_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "generate_stories",
                "approved_evidence": approved_evidence,
                "profile_context": profile_context,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            evidence = approved_evidence[0]
            evidence_id = int(evidence["id"])
            action = evidence.get("action") or evidence.get("source_excerpt") or "I led the work."
            result = (
                evidence.get("result") or evidence.get("metric") or "The work improved outcomes."
            )
            return {
                "stories": [
                    {
                        "client_story_id": "story-1",
                        "title": evidence.get("title") or "Reusable story",
                        "story_type": "GENERAL",
                        "situation": evidence.get("problem"),
                        "task": evidence.get("role"),
                        "action": action,
                        "result": result,
                        "learning": None,
                        "short_answer": f"{action} {result}",
                        "ninety_second_answer": f"{action} {result}",
                        "detailed_answer": f"{action} {result}",
                        "competency_tags": evidence.get("competencies") or [],
                        "seniority_signals": [],
                        "evidence_ids": [evidence_id],
                        "missing_details": [],
                    }
                ]
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def score_stories(
        self,
        *,
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "score_stories",
                "stories": stories,
                "approved_evidence": approved_evidence,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            return {
                "scores": [
                    {
                        "client_story_id": story["client_story_id"],
                        "specificity_score": 80,
                        "impact_score": 80,
                        "ownership_score": 80,
                        "clarity_score": 80,
                        "missing_details": [],
                        "scoring_notes": None,
                    }
                    for story in stories
                ]
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def score_story_matches(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        competency_map: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "score_story_matches",
                "opportunity_context": opportunity_context,
                "role_pack": role_pack,
                "competency_map": competency_map,
                "stories": stories,
                "approved_evidence": approved_evidence,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            story_id = stories[0]["id"] if stories else None
            evidence_ids = stories[0].get("evidence_ids", []) if stories else []
            return {
                "matches": [
                    {
                        "competency_key": item["key"],
                        "primary_story_id": story_id,
                        "alternative_story_id": None,
                        "competency_score": 75,
                        "role_relevance_score": 75,
                        "seniority_score": 70,
                        "evidence_strength_score": 70,
                        "company_context_score": 60,
                        "explanation": "This story credibly supports the competency.",
                        "jd_excerpt": None,
                        "evidence_ids": evidence_ids,
                        "missing_signal": None,
                        "recommended_emphasis": "Emphasize the evidence-backed outcome.",
                    }
                    for item in competency_map
                ]
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_preview(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        matched_story_excerpt_source: dict,
        deterministic_counts: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "generate_preview",
                "opportunity_context": opportunity_context,
                "role_pack": role_pack,
                "matches": matches,
                "stories": stories,
                "approved_evidence": approved_evidence,
                "matched_story_excerpt_source": matched_story_excerpt_source,
                "deterministic_counts": deterministic_counts,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            match = matches[0]
            story = stories[0]
            evidence_ids = story.get("evidence_ids", [])
            return {
                "role_summary": "This preview summarizes readiness for the confirmed role.",
                "competencies": [
                    {
                        "key": f"{(matches[index % len(matches)])['competency_key']}_{index}",
                        "label": (
                            (matches[index % len(matches)]).get("competency_label")
                            or (matches[index % len(matches)])["competency_key"]
                        ),
                        "readiness": "covered"
                        if (matches[index % len(matches)]).get("primary_story_id")
                        else "gap",
                        "source_match_id": (matches[index % len(matches)])["id"],
                        "evidence_ids": (matches[index % len(matches)]).get("evidence_ids") or [],
                        "story_ids": [(matches[index % len(matches)])["primary_story_id"]]
                        if (matches[index % len(matches)]).get("primary_story_id")
                        else [],
                    }
                    for index in range(5)
                ],
                "strengths": [
                    {
                        "title": f"Evidence-backed story coverage {index + 1}",
                        "explanation": "At least one reusable story maps to the role context.",
                        "source_match_id": match["id"],
                        "evidence_ids": match.get("evidence_ids") or evidence_ids,
                        "story_ids": [story["id"]],
                    }
                    for index in range(3)
                ],
                "gaps": [
                    {
                        "title": f"Sharpen missing signals {index + 1}",
                        "explanation": (
                            "Use the Prep Kit to turn weaker signals into focused "
                            "practice priorities."
                        ),
                        "recommended_next_step": (
                            "Review the weakest competency before interview practice."
                        ),
                        "source_match_id": match["id"],
                        "evidence_ids": [],
                        "story_ids": [],
                    }
                    for index in range(3)
                ],
                "evidence_completeness": {
                    "approved_evidence_count": deterministic_counts["approved_evidence_count"],
                    "result_backed_evidence_count": deterministic_counts[
                        "result_backed_evidence_count"
                    ],
                    "competencies_with_evidence_count": deterministic_counts[
                        "competencies_with_evidence_count"
                    ],
                    "summary": "Approved evidence is available for preview generation.",
                },
                "story_coverage": {
                    "ready_story_count": deterministic_counts["ready_story_count"],
                    "matched_competency_count": deterministic_counts["matched_competency_count"],
                    "gap_competency_count": deterministic_counts["gap_competency_count"],
                    "summary": "Reusable stories cover part of the role context.",
                },
                "matched_story_excerpt": matched_story_excerpt_source,
                "prepkit_explanation": (
                    "The paid Prep Kit will expand this preview into focused questions, "
                    "story guidance, and practice priorities after payment is implemented."
                ),
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_prepkit_analysis(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "generate_prepkit_analysis",
                "opportunity_context": opportunity_context,
                "role_pack": role_pack,
                "matches": matches,
                "stories": stories,
                "approved_evidence": approved_evidence,
                "preview": preview,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            evidence_id = int(approved_evidence[0]["id"])
            story_id = int(stories[0]["id"])
            match_id = int(matches[0]["id"])
            ref = {"source_type": "evidence", "source_id": evidence_id, "source_field": "title"}
            item = {
                "title": "Grounded preparation focus",
                "detail": "Use the approved story and evidence to prepare for this role.",
                "source_refs": [ref],
                "evidence_ids": [evidence_id],
                "story_ids": [story_id],
                "match_ids": [match_id],
            }
            return {
                "role_briefing_points": [item],
                "fit_findings": [item],
                "competency_findings": [item],
                "story_recommendations": [item],
                "question_themes": [item],
                "concern_findings": [item],
                "missing_evidence_findings": [item],
                "practice_priority_findings": [item],
                "seven_day_focus_areas": [item],
                "checklist_findings": [item],
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_prepkit_artifact(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        analysis: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "generate_prepkit_artifact",
                "opportunity_context": opportunity_context,
                "role_pack": role_pack,
                "matches": matches,
                "stories": stories,
                "approved_evidence": approved_evidence,
                "preview": preview,
                "analysis": analysis,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            evidence_id = int(approved_evidence[0]["id"])
            story_id = int(stories[0]["id"])
            match_id = int(matches[0]["id"])
            ref = {"source_type": "evidence", "source_id": evidence_id, "source_field": "title"}
            item = {
                "title": "Grounded preparation focus",
                "detail": "Use the approved story and evidence to prepare for this role.",
                "source_refs": [ref],
                "evidence_ids": [evidence_id],
                "story_ids": [story_id],
                "match_ids": [match_id],
            }
            return {
                "role_briefing": {
                    "role_title": opportunity_context.get("role_title") or "Target role",
                    "company_name": opportunity_context.get("company_name"),
                    "briefing": (
                        "Prepare for the confirmed role using approved evidence and "
                        "matched stories."
                    ),
                    "source_refs": [ref],
                },
                "fit_summary": {
                    "summary": "Your fit is grounded in approved stories.",
                    "strengths": [item],
                    "gaps": [item],
                },
                "competency_coverage": [
                    {
                        **item,
                        "competency_key": matches[0].get("competency_key") or "competency",
                        "coverage_level": "covered",
                    }
                ],
                "story_map": [
                    {**item, "recommended_story_id": story_id, "question_types": ["Behavioral"]}
                ],
                "question_bank": [
                    {
                        **item,
                        "question": "Tell me about the approved story.",
                        "recommended_story_id": story_id,
                        "priority": "high",
                    }
                ],
                "concern_map": [
                    {**item, "concern": opportunity_context.get("concerns") or "Role readiness"}
                ],
                "missing_evidence": [
                    {
                        **item,
                        "suggested_detail": "Add more detail if the interviewer asks for depth.",
                    }
                ],
                "practice_priorities": [{**item, "priority_order": 1}],
                "seven_day_plan": [
                    {
                        "day_number": day,
                        "focus": "Focused preparation",
                        "tasks": [item],
                    }
                    for day in range(1, 8)
                ],
                "interview_checklist": [{**item, "category": "stories"}],
            }
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def evaluate_answer(
        self,
        *,
        question: dict,
        answer_text: str,
        linked_story: dict | None,
        approved_evidence: list[dict],
        prepkit_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "operation": "evaluate_answer",
                "question": question,
                "answer_text": answer_text,
                "linked_story": linked_story,
                "approved_evidence": approved_evidence,
                "prepkit_context": prepkit_context,
                "retry_context": retry_context,
            }
        )
        if not self.responses:
            improved = linked_story.get("short_answer") if linked_story else answer_text
            return {
                "relevance_score": 4,
                "structure_score": 4,
                "specificity_score": 4,
                "ownership_score": 4,
                "impact_score": 4,
                "clarity_score": 4,
                "strengths": ["The answer addresses the selected question."],
                "improvements": ["Add a clearer result from approved evidence."],
                "improved_answer": improved or answer_text,
                "follow_up_question": "What result would you emphasize next?",
                "unsupported_claims": [],
                "source_refs": [
                    {
                        "source_type": "question",
                        "source_id": question.get("question_id"),
                        "source_field": "question",
                    }
                ],
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


class OpenAIEvidenceClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.EVIDRA_OPENAI_MODEL
        if not self.api_key:
            raise AIClientError("OpenAI API key is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def extract_evidence(
        self,
        *,
        resume_text: str,
        highlights: list[dict],
        profile_context: dict,
        opportunity_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.evidence import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "resume_text": resume_text,
            "highlights": highlights,
            "profile_context": profile_context,
            "opportunity_context": opportunity_context,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extracted_evidence",
                        "schema": ExtractedEvidenceSet.model_json_schema(),
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
            raise AIClientError("Evidence extraction failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Evidence extraction returned invalid JSON.")
        return parsed


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

    def generate_prepkit_analysis(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.prepkit import ANALYSIS_SYSTEM_PROMPT

        prompt = ANALYSIS_SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "opportunity_context": opportunity_context,
            "role_pack": role_pack,
            "matches": matches,
            "stories": stories,
            "approved_evidence": approved_evidence,
            "preview": preview,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "prepkit_analysis",
                        "schema": PrepKitAnalysisOutput.model_json_schema(),
                        "strict": True,
                    },
                },
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001
            raise AIClientError("Prep Kit analysis generation failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Prep Kit analysis generation returned invalid JSON.")
        return parsed

    def generate_prepkit_artifact(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        preview: dict,
        analysis: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.prepkit import ARTIFACT_SYSTEM_PROMPT

        prompt = ARTIFACT_SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "opportunity_context": opportunity_context,
            "role_pack": role_pack,
            "matches": matches,
            "stories": stories,
            "approved_evidence": approved_evidence,
            "preview": preview,
            "analysis": analysis,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "prepkit_artifact",
                        "schema": PrepKitArtifactOutput.model_json_schema(),
                        "strict": True,
                    },
                },
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001
            raise AIClientError("Prep Kit artifact generation failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Prep Kit artifact generation returned invalid JSON.")
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


class OpenAIStoryClient:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.EVIDRA_OPENAI_MODEL
        if not self.api_key:
            raise AIClientError("OpenAI API key is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def generate_stories(
        self,
        *,
        approved_evidence: list[dict],
        profile_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.stories import GENERATE_STORIES_SYSTEM_PROMPT

        prompt = GENERATE_STORIES_SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "approved_evidence": approved_evidence,
            "profile_context": profile_context,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "generated_stories",
                        "schema": GeneratedStorySet.model_json_schema(),
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
            raise AIClientError("Story generation failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Story generation returned invalid JSON.")
        return parsed

    def score_stories(
        self,
        *,
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.stories import SCORE_STORIES_SYSTEM_PROMPT

        prompt = SCORE_STORIES_SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "stories": stories,
            "approved_evidence": approved_evidence,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "story_scores",
                        "schema": StoryScoreSet.model_json_schema(),
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
            raise AIClientError("Story scoring failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Story scoring returned invalid JSON.")
        return parsed

    def score_story_matches(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        competency_map: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.matching import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "opportunity_context": opportunity_context,
            "role_pack": role_pack,
            "competency_map": competency_map,
            "stories": stories,
            "approved_evidence": approved_evidence,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "story_matches",
                        "schema": StoryMatchSet.model_json_schema(),
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
            raise AIClientError("Story match scoring failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Story match scoring returned invalid JSON.")
        return parsed

    def evaluate_answer(
        self,
        *,
        question: dict,
        answer_text: str,
        linked_story: dict | None,
        approved_evidence: list[dict],
        prepkit_context: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.practice import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "question": question,
            "answer_text": answer_text,
            "linked_story": linked_story,
            "approved_evidence": approved_evidence,
            "prepkit_context": prepkit_context,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "practice_feedback",
                        "schema": PracticeFeedbackOutput.model_json_schema(),
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
            raise AIClientError("Practice answer evaluation failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Practice answer evaluation returned invalid JSON.")
        return parsed

    def generate_preview(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        matches: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
        matched_story_excerpt_source: dict,
        deterministic_counts: dict,
        retry_context: str | None = None,
    ) -> dict:
        from ai.prompts.preview import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT
        if retry_context:
            prompt += f" Previous output was structurally invalid: {retry_context}."
        user_payload = {
            "opportunity_context": opportunity_context,
            "role_pack": role_pack,
            "matches": matches,
            "stories": stories,
            "approved_evidence": approved_evidence,
            "matched_story_excerpt_source": matched_story_excerpt_source,
            "deterministic_counts": deterministic_counts,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "readiness_preview",
                        "schema": ReadinessPreviewOutput.model_json_schema(),
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
            raise AIClientError("Readiness preview generation failed.") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("Readiness preview generation returned invalid JSON.")
        return parsed
