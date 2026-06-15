from apps.evidence.models import EvidenceCard, EvidenceStatus
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
from apps.sprints.models import SprintState
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


def make_evidence_approved_sprint(username="stories@example.com"):
    user, sprint, profile = make_profile_confirmed_sprint(username)
    Opportunity.objects.create(
        sprint=sprint,
        **opportunity_data(),
        jd_analysis=jd_analysis_dict(),
        company_context_status=CompanyContextStatus.SKIPPED,
        confirmation_status=OpportunityStatus.CONFIRMED,
    )
    sprint.state = SprintState.EVIDENCE_APPROVED
    sprint.save(update_fields=["state", "updated_at"])
    excerpt = "Experience leading product teams and delivering customer outcomes."
    for index in range(3):
        EvidenceCard.objects.create(
            user=user,
            profile=profile,
            source_document=sprint.active_resume,
            title=f"Evidence {index}",
            problem="Customers needed better onboarding",
            role="Product lead",
            action="Led product teams",
            result="Delivered customer outcomes" if index < 2 else "",
            metric=None,
            competencies=["Execution"],
            source_excerpt=excerpt,
            source_location="resume",
            status=EvidenceStatus.APPROVED,
        )
    return user, sprint, profile


def generated_story(evidence_id, *, metric=None):
    return {
        "client_story_id": "story-1",
        "title": "Delivered outcomes",
        "story_type": "IMPACT",
        "situation": "Customers needed better onboarding",
        "task": "Product lead",
        "action": "Led product teams",
        "result": f"Improved activation by {metric}" if metric else "Delivered outcomes",
        "learning": None,
        "short_answer": "I led product teams and delivered customer outcomes.",
        "ninety_second_answer": "I led product teams and delivered customer outcomes.",
        "detailed_answer": "I led product teams and delivered customer outcomes.",
        "competency_tags": ["Execution"],
        "seniority_signals": ["Ownership"],
        "evidence_ids": [evidence_id],
        "missing_details": [],
    }


def story_score(client_story_id="story-1"):
    return {
        "client_story_id": client_story_id,
        "specificity_score": 80,
        "impact_score": 90,
        "ownership_score": 70,
        "clarity_score": 80,
        "missing_details": [],
        "scoring_notes": None,
    }
