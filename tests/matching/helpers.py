from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
from apps.sprints.models import SprintState
from apps.stories.models import Story, StoryStatus
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


def make_stories_ready_sprint(username="matching@example.com"):
    user, sprint, profile = make_profile_confirmed_sprint(username)
    Opportunity.objects.create(
        sprint=sprint,
        **opportunity_data(job_description="Lead product strategy and cross-functional execution."),
        jd_analysis=jd_analysis_dict(),
        company_context_status=CompanyContextStatus.SKIPPED,
        confirmation_status=OpportunityStatus.CONFIRMED,
    )
    evidence = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Product strategy evidence",
        problem="Teams lacked onboarding clarity",
        role="Product lead",
        action="Led product strategy and cross-functional execution",
        result="Improved onboarding outcomes",
        competencies=["Product strategy"],
        source_excerpt="Led product strategy and cross-functional execution.",
        source_location="resume",
        status=EvidenceStatus.APPROVED,
    )
    story = Story.objects.create(
        user=user,
        profile=profile,
        title="Led product strategy",
        story_type="IMPACT",
        action="Led product strategy and cross-functional execution",
        result="Improved onboarding outcomes",
        short_answer="I led product strategy and execution.",
        ninety_second_answer="I led product strategy and execution.",
        detailed_answer="I led product strategy and execution.",
        competency_tags=["Product strategy"],
        seniority_signals=["Ownership"],
        evidence_ids=[evidence.id],
        specificity_score=80,
        impact_score=80,
        ownership_score=80,
        clarity_score=80,
        quality_score=80,
        status=StoryStatus.READY,
    )
    alternative = Story.objects.create(
        user=user,
        profile=profile,
        title="Alternative execution story",
        story_type="IMPACT",
        action="Led execution",
        result="Improved delivery",
        short_answer="I led execution.",
        ninety_second_answer="I led execution.",
        detailed_answer="I led execution.",
        competency_tags=["Execution"],
        seniority_signals=["Ownership"],
        evidence_ids=[evidence.id],
        quality_score=75,
        status=StoryStatus.READY,
    )
    sprint.state = SprintState.STORIES_READY
    sprint.save(update_fields=["state", "updated_at"])
    return user, sprint, profile, evidence, story, alternative


def match_response(story, evidence, *, key="product_strategy", alternative=None, score=80):
    return {
        "matches": [
            {
                "competency_key": key,
                "primary_story_id": story.id if story else None,
                "alternative_story_id": alternative.id if alternative else None,
                "competency_score": score,
                "role_relevance_score": score,
                "seniority_score": score,
                "evidence_strength_score": score,
                "company_context_score": score,
                "explanation": "This story is a strong fit."
                if score >= 80
                else "This story partially fits.",
                "jd_excerpt": "Lead product strategy",
                "evidence_ids": [evidence.id] if evidence else [],
                "missing_signal": None if story else "Add a credible product strategy story.",
                "recommended_emphasis": "Emphasize the evidence-backed outcome.",
            }
        ]
    }
