from django.contrib.auth import get_user_model

from apps.documents.models import Document, DocumentParsingStatus
from apps.profiles.models import CareerProfile, CareerProfileStatus
from apps.sprints.models import InterviewSprint, SprintState


def jd_text():
    return (
        "We need a product leader to define strategy, run discovery, prioritize roadmap work, "
        "collaborate with engineering and design, and measure customer outcomes. " * 2
    )


def make_profile_confirmed_sprint(username="user@example.com", password=None):
    user = get_user_model().objects.create_user(username=username, password=password)
    document = Document.objects.create(
        user=user,
        cleaned_text="Experience leading product teams and delivering customer outcomes. " * 5,
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )
    profile = CareerProfile.objects.create(
        user=user,
        active_resume=document,
        confirmation_status=CareerProfileStatus.CONFIRMED,
    )
    sprint = InterviewSprint.objects.create(
        user=user,
        state=SprintState.PROFILE_CONFIRMED,
        active_resume=document,
        active_profile=profile,
    )
    return user, sprint, profile


def opportunity_data(**overrides):
    data = {
        "role_title": "Senior Product Manager",
        "role_family": "PRODUCT_MANAGEMENT",
        "target_seniority": "Senior",
        "company_name": "ExampleCo",
        "job_description": jd_text(),
        "interview_stage": "Hiring manager",
        "interview_date": "2026-07-01",
        "concerns": "Need sharper prioritization stories.",
        "improvement_goals": "Improve strategic framing.",
    }
    data.update(overrides)
    return data


def jd_analysis_dict():
    return {
        "summary": "The role emphasizes product strategy and customer discovery.",
        "competencies": [
            {
                "name": "Product strategy",
                "description": "Define product direction.",
                "source_excerpt": "define strategy",
            }
        ],
        "skills": [{"name": "Discovery", "category": "domain", "source_excerpt": "run discovery"}],
        "seniority_expectations": [
            {
                "expectation": "Lead cross-functional roadmap decisions.",
                "source_excerpt": "prioritize roadmap work",
            }
        ],
        "likely_themes": [{"theme": "Customer outcomes", "source_excerpt": "customer outcomes"}],
        "uncertain_fields": [],
    }
