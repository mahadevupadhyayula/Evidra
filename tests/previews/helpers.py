from apps.matching.models import StoryMatch
from apps.sprints.models import SprintState
from tests.matching.helpers import make_stories_ready_sprint


def make_matching_ready_sprint(username="preview@example.com"):
    user, sprint, profile, evidence, story, alternative = make_stories_ready_sprint(username)
    sprint.state = SprintState.MATCHING_READY
    sprint.save(update_fields=["state", "updated_at"])
    match = StoryMatch.objects.create(
        sprint=sprint,
        competency_key="product_strategy",
        competency_label="Product strategy",
        primary_story=story,
        alternative_story=alternative,
        competency_score=80,
        role_relevance_score=80,
        seniority_score=75,
        evidence_strength_score=75,
        company_context_score=60,
        total_score=78,
        explanation="This story credibly supports the role.",
        jd_excerpt="Lead product strategy",
        evidence_ids=[evidence.id],
        recommended_emphasis="Emphasize the evidence-backed outcome.",
    )
    return user, sprint, profile, evidence, story, alternative, match


def preview_response(match, story, evidence):
    competency_names = [
        ("product_strategy", "Product strategy"),
        ("execution", "Execution"),
        ("collaboration", "Collaboration"),
        ("customer_focus", "Customer focus"),
        ("communication", "Communication"),
    ]
    competencies = [
        {
            "key": key,
            "label": label,
            "readiness": "covered" if index == 0 else "partial",
            "source_match_id": match.id,
            "evidence_ids": [evidence.id] if index == 0 else [],
            "story_ids": [story.id] if index == 0 else [],
        }
        for index, (key, label) in enumerate(competency_names)
    ]
    strength_titles = ["Evidence-backed strategy", "Reusable story", "Clear ownership"]
    strengths = [
        {
            "title": title,
            "explanation": "The selected story is grounded in approved evidence.",
            "source_match_id": match.id,
            "evidence_ids": [evidence.id],
            "story_ids": [story.id],
        }
        for title in strength_titles
    ]
    gap_titles = ["Sharper role detail", "More practice focus", "Stronger closing emphasis"]
    gaps = [
        {
            "title": title,
            "explanation": "The answer can be sharpened for the target role.",
            "recommended_next_step": "Use the Prep Kit to turn this into practice priorities.",
            "source_match_id": match.id,
            "evidence_ids": [],
            "story_ids": [],
        }
        for title in gap_titles
    ]
    return {
        "role_summary": "This role emphasizes product strategy and cross-functional execution.",
        "competencies": competencies,
        "strengths": strengths,
        "gaps": gaps,
        "evidence_completeness": {
            "approved_evidence_count": 1,
            "result_backed_evidence_count": 1,
            "competencies_with_evidence_count": 1,
            "summary": "Approved evidence supports this preview.",
        },
        "story_coverage": {
            "ready_story_count": 2,
            "matched_competency_count": 1,
            "gap_competency_count": 0,
            "summary": "Reusable stories cover the top competency.",
        },
        "matched_story_excerpt": {
            "story_id": story.id,
            "match_id": match.id,
            "title": story.title,
            "excerpt": story.short_answer,
            "evidence_ids": [evidence.id],
        },
        "prepkit_explanation": (
            "The paid Prep Kit will expand this preview into questions and "
            "practice priorities after payment is available."
        ),
    }
