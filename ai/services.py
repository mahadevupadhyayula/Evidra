from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from ai.client import (
    AIClientError,
    CompanyContextExtractionClient,
    EvidenceExtractionClient,
    JDAnalysisClient,
    OpenAICompanyContextClient,
    OpenAIEvidenceClient,
    OpenAIJDClient,
    OpenAIProfileClient,
    OpenAIStoryClient,
    PreviewGenerationClient,
    ProfileExtractionClient,
    StoryGenerationClient,
    StoryMatchScoringClient,
    StoryScoringClient,
)
from ai.schemas.company_context import CompanyContext
from ai.schemas.evidence import ExtractedEvidenceSet
from ai.schemas.jd import JDAnalysis
from ai.schemas.matching import StoryMatchSet
from ai.schemas.preview import ReadinessPreviewOutput
from ai.schemas.profile import ExtractedProfile
from ai.schemas.stories import GeneratedStorySet, StoryScoreSet


class AIProfileExtractionError(RuntimeError):
    """Raised when profile extraction cannot produce valid structured output."""


class AIJDAnalysisError(RuntimeError):
    """Raised when JD analysis cannot produce valid structured output."""


class AICompanyContextExtractionError(RuntimeError):
    """Raised when company context extraction cannot produce valid structured output."""


class AIEvidenceExtractionError(RuntimeError):
    """Raised when evidence extraction cannot produce valid structured output."""


class AIStoryGenerationError(RuntimeError):
    """Raised when story generation cannot produce valid structured output."""


class AIStoryScoringError(RuntimeError):
    """Raised when story scoring cannot produce valid structured output."""


class AIStoryMatchScoringError(RuntimeError):
    """Raised when story matching cannot produce valid structured output."""


class AIPreviewGenerationError(RuntimeError):
    """Raised when readiness preview generation cannot produce valid structured output."""


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


def _grounding_text_from_values(*values: object) -> str:
    parts: list[str] = []

    def collect(value: object) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        parts.append(str(value))

    for value in values:
        collect(value)
    return " ".join(parts).casefold()


def _validate_match_narrative_numeric_claims(matches: StoryMatchSet, grounding_text: str) -> None:
    for match in matches.matches:
        for value in [match.explanation, match.missing_signal, match.recommended_emphasis]:
            if not value:
                continue
            for numeric_claim in NUMERIC_CLAIM_PATTERN.finditer(value):
                if numeric_claim.group(0).casefold() not in grounding_text:
                    raise ValueError("Story match narrative contains an unsupported numeric claim.")


@dataclass(frozen=True)
class EvidraAIService:
    client: (
        ProfileExtractionClient
        | JDAnalysisClient
        | CompanyContextExtractionClient
        | EvidenceExtractionClient
        | StoryGenerationClient
        | StoryScoringClient
        | StoryMatchScoringClient
        | PreviewGenerationClient
        | None
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

    def extract_evidence(
        self,
        *,
        resume_text: str,
        highlights: list[dict],
        profile_context: dict,
        opportunity_context: dict,
    ) -> ExtractedEvidenceSet:
        source_text = resume_text.strip()
        if not source_text and not highlights:
            raise AIEvidenceExtractionError("Resume text or highlights are required.")

        client = self.client or OpenAIEvidenceClient()
        if not hasattr(client, "extract_evidence"):
            raise AIEvidenceExtractionError("Evidence extraction client is not configured.")

        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_evidence = client.extract_evidence(
                    resume_text=source_text,
                    highlights=highlights,
                    profile_context=profile_context,
                    opportunity_context=opportunity_context,
                    retry_context=retry_context,
                )
                evidence = ExtractedEvidenceSet.model_validate(raw_evidence)
                return ground_evidence_in_sources(evidence, source_text, highlights)
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIEvidenceExtractionError(
            "Evidence extraction returned invalid structured output."
        ) from last_error

    def generate_stories(
        self,
        *,
        approved_evidence: list[dict],
        profile_context: dict,
    ) -> GeneratedStorySet:
        if not approved_evidence:
            raise AIStoryGenerationError("Approved evidence is required for story generation.")

        client = self.client or OpenAIStoryClient()
        if not hasattr(client, "generate_stories"):
            raise AIStoryGenerationError("Story generation client is not configured.")

        evidence_ids = {int(item["id"]) for item in approved_evidence}
        evidence_text = _approved_evidence_grounding_text(approved_evidence)
        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_stories = client.generate_stories(
                    approved_evidence=approved_evidence,
                    profile_context=profile_context,
                    retry_context=retry_context,
                )
                stories = GeneratedStorySet.model_validate(raw_stories)
                _validate_story_references(stories, evidence_ids)
                _validate_story_numeric_claims(stories, evidence_text)
                return stories
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIStoryGenerationError(
            "Story generation returned invalid structured output."
        ) from last_error

    def score_stories(
        self,
        *,
        stories: list[dict],
        approved_evidence: list[dict],
    ) -> StoryScoreSet:
        if not stories:
            raise AIStoryScoringError("Stories are required for scoring.")

        client = self.client or OpenAIStoryClient()
        if not hasattr(client, "score_stories"):
            raise AIStoryScoringError("Story scoring client is not configured.")

        story_ids = {str(item["client_story_id"]) for item in stories}
        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_scores = client.score_stories(
                    stories=stories,
                    approved_evidence=approved_evidence,
                    retry_context=retry_context,
                )
                scores = StoryScoreSet.model_validate(raw_scores)
                score_ids = {score.client_story_id for score in scores.scores}
                if score_ids != story_ids:
                    raise ValueError("Story scoring must cover each generated story exactly once.")
                return scores
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIStoryScoringError(
            "Story scoring returned invalid structured output."
        ) from last_error

    def score_story_matches(
        self,
        *,
        opportunity_context: dict,
        role_pack: dict,
        competency_map: list[dict],
        stories: list[dict],
        approved_evidence: list[dict],
    ) -> StoryMatchSet:
        if not competency_map:
            raise AIStoryMatchScoringError("Competency map is required for matching.")
        if not stories:
            raise AIStoryMatchScoringError("Stories are required for matching.")

        client = self.client or OpenAIStoryClient()
        if not hasattr(client, "score_story_matches"):
            raise AIStoryMatchScoringError("Story match scoring client is not configured.")

        competency_keys = {str(item["key"]) for item in competency_map}
        story_ids = {int(item["id"]) for item in stories}
        evidence_ids = {int(item["id"]) for item in approved_evidence}
        jd_text = str(opportunity_context.get("job_description") or "")
        normalized_jd = jd_text.casefold()
        grounding_text = _grounding_text_from_values(
            opportunity_context, role_pack, competency_map, stories, approved_evidence
        )
        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_matches = client.score_story_matches(
                    opportunity_context=opportunity_context,
                    role_pack=role_pack,
                    competency_map=competency_map,
                    stories=stories,
                    approved_evidence=approved_evidence,
                    retry_context=retry_context,
                )
                matches = StoryMatchSet.model_validate(raw_matches)
                match_keys = {match.competency_key for match in matches.matches}
                if not match_keys.issubset(competency_keys):
                    raise ValueError("Story matches reference an unknown competency key.")
                for match in matches.matches:
                    for story_id in [match.primary_story_id, match.alternative_story_id]:
                        if story_id is not None and int(story_id) not in story_ids:
                            raise ValueError("Story matches reference an unknown story.")
                    if not set(match.evidence_ids).issubset(evidence_ids):
                        raise ValueError("Story matches reference unknown evidence.")
                    if match.jd_excerpt and match.jd_excerpt.casefold() not in normalized_jd:
                        raise ValueError(
                            "Story match JD excerpt must come from the job description."
                        )
                _validate_match_narrative_numeric_claims(matches, grounding_text)
                return matches
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIStoryMatchScoringError(
            "Story matching returned invalid structured output."
        ) from last_error

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
    ) -> ReadinessPreviewOutput:
        if not matches:
            raise AIPreviewGenerationError("Contextual matches are required for preview.")
        if not stories:
            raise AIPreviewGenerationError("Stories are required for preview.")
        if not approved_evidence:
            raise AIPreviewGenerationError("Approved evidence is required for preview.")

        client = self.client or OpenAIStoryClient()
        if not hasattr(client, "generate_preview"):
            raise AIPreviewGenerationError("Readiness preview client is not configured.")

        last_error: Exception | None = None
        retry_context: str | None = None
        for _attempt in range(2):
            try:
                raw_preview = client.generate_preview(
                    opportunity_context=opportunity_context,
                    role_pack=role_pack,
                    matches=matches,
                    stories=stories,
                    approved_evidence=approved_evidence,
                    matched_story_excerpt_source=matched_story_excerpt_source,
                    deterministic_counts=deterministic_counts,
                    retry_context=retry_context,
                )
                return ReadinessPreviewOutput.model_validate(raw_preview)
            except (AIClientError, ValidationError, ValueError) as exc:
                last_error = exc
                retry_context = str(exc)
        raise AIPreviewGenerationError(
            "Readiness preview generation returned invalid structured output."
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


def ground_evidence_in_sources(
    evidence: ExtractedEvidenceSet, resume_text: str, highlights: list[dict]
) -> ExtractedEvidenceSet:
    normalized_resume = _normalize_grounding_text(resume_text)
    highlights_by_id = {int(item["id"]): item for item in highlights if item.get("id") is not None}
    grounded_cards = []
    for card in evidence.cards:
        normalized_excerpt = _normalize_grounding_text(card.source_excerpt)
        if card.source_type == "resume":
            if not normalized_excerpt or normalized_excerpt not in normalized_resume:
                raise ValueError("Evidence source excerpts must appear in the confirmed resume.")
            source_blob = normalized_resume
        else:
            highlight = highlights_by_id.get(int(card.source_highlight_id or 0))
            if highlight is None:
                raise ValueError("Highlight evidence must reference a provided highlight.")
            source_blob = _normalize_grounding_text(
                " ".join(
                    str(highlight.get(field) or "")
                    for field in ["title", "description", "metric", "source_note"]
                )
            )
            if not normalized_excerpt or normalized_excerpt not in source_blob:
                raise ValueError("Evidence source excerpts must appear in the source highlight.")

        missing_details = list(card.missing_details)
        metric = card.metric
        if metric and _normalize_grounding_text(metric) not in source_blob:
            metric = None
            if "Confirm the metric for this evidence." not in missing_details:
                missing_details.append("Confirm the metric for this evidence.")
        grounded_cards.append(
            card.model_copy(update={"metric": metric, "missing_details": missing_details})
        )
    return evidence.model_copy(update={"cards": grounded_cards})


def _approved_evidence_grounding_text(approved_evidence: list[dict]) -> str:
    parts: list[str] = []
    for item in approved_evidence:
        for field in [
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
        ]:
            value = item.get(field)
            if value:
                parts.append(str(value))
    return _normalize_grounding_text(" ".join(parts))


def _validate_story_references(stories: GeneratedStorySet, evidence_ids: set[int]) -> None:
    for story in stories.stories:
        if not story.evidence_ids:
            raise ValueError("Stories must reference approved evidence.")
        unknown_ids = set(story.evidence_ids) - evidence_ids
        if unknown_ids:
            raise ValueError("Stories must reference only provided approved evidence.")


def _validate_story_numeric_claims(
    stories: GeneratedStorySet, normalized_evidence_text: str
) -> None:
    for story in stories.stories:
        for value in [
            story.situation,
            story.task,
            story.action,
            story.result,
            story.learning,
            story.short_answer,
            story.ninety_second_answer,
            story.detailed_answer,
        ]:
            if value and _has_unsupported_story_numeric_claim(value, normalized_evidence_text):
                raise ValueError("Story numeric claims must trace to approved evidence.")


def _has_unsupported_story_numeric_claim(value: str, normalized_evidence_text: str) -> bool:
    for match in NUMERIC_CLAIM_PATTERN.finditer(value):
        normalized_claim = _normalize_grounding_text(match.group(0))
        if normalized_claim and normalized_claim not in normalized_evidence_text:
            return True
    return False
