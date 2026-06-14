import pytest
from django.contrib.auth import get_user_model
from django.http import Http404

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.evidence.models import (
    CareerHighlight,
    CareerHighlightStatus,
    EvidenceCard,
    EvidenceStatus,
)
from apps.evidence.services import EvidenceError, EvidenceService
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
from apps.sprints.models import SprintState
from apps.sprints.services import SprintTransitionConditionMissing
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


def make_opportunity_confirmed_sprint(username="evidence@example.com"):
    user, sprint, profile = make_profile_confirmed_sprint(username)
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        **opportunity_data(),
        jd_analysis=jd_analysis_dict(),
        company_context_status=CompanyContextStatus.SKIPPED,
        confirmation_status=OpportunityStatus.CONFIRMED,
    )
    sprint.state = SprintState.OPPORTUNITY_CONFIRMED
    sprint.save(update_fields=["state", "updated_at"])
    return user, sprint, profile, opportunity


@pytest.mark.django_db
def test_create_highlight_transitions_to_evidence_review():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()

    highlight = EvidenceService.create_highlight(
        user=user,
        sprint=sprint,
        cleaned_data={
            "title": "Launched onboarding",
            "description": "Led onboarding launch that improved activation for new customers.",
            "metric": "20%",
            "skills_text": ["Product"],
            "source_note": "User supplied detail",
        },
    )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.EVIDENCE_REVIEW
    assert highlight.user == user
    assert highlight.profile == profile


@pytest.mark.django_db
def test_extract_evidence_creates_review_cards_without_approving():
    user, sprint, _profile, _opportunity = make_opportunity_confirmed_sprint()
    excerpt = "Experience leading product teams and delivering customer outcomes."
    client = MockAIClient(
        responses=[
            {
                "cards": [
                    {
                        "title": "Delivered outcomes",
                        "problem": "Customers needed results",
                        "role": "Product lead",
                        "action": "Led product teams",
                        "result": "Delivered customer outcomes",
                        "metric": None,
                        "skills": ["Product"],
                        "competencies": ["Execution"],
                        "ownership_signal": "Led",
                        "constraints": None,
                        "tradeoffs": None,
                        "missing_details": [],
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
        ]
    )

    count = EvidenceService.extract_evidence(
        user=user,
        sprint=sprint,
        ai_service=EvidraAIService(client=client),
    )

    sprint.refresh_from_db()
    card = EvidenceCard.objects.get(user=user)
    assert count == 1
    assert sprint.state == SprintState.EVIDENCE_REVIEW
    assert card.status == EvidenceStatus.DRAFT
    assert card.source_document == sprint.active_resume


@pytest.mark.django_db
def test_threshold_requires_three_approved_cards_with_two_clear_results():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    excerpt = "Experience leading product teams and delivering customer outcomes."
    for index in range(3):
        EvidenceCard.objects.create(
            user=user,
            profile=profile,
            source_document=sprint.active_resume,
            title=f"Evidence {index}",
            result="Clear result" if index < 2 else "",
            source_excerpt=excerpt,
            status=EvidenceStatus.APPROVED,
        )

    threshold = EvidenceService.approve_evidence_set(user=user, sprint=sprint)

    sprint.refresh_from_db()
    assert threshold.is_met
    assert sprint.state == SprintState.EVIDENCE_APPROVED


@pytest.mark.django_db
def test_threshold_rejects_insufficient_clear_results():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    excerpt = "Experience leading product teams and delivering customer outcomes."
    for index in range(3):
        EvidenceCard.objects.create(
            user=user,
            profile=profile,
            source_document=sprint.active_resume,
            title=f"Evidence {index}",
            result="Clear result" if index == 0 else "",
            source_excerpt=excerpt,
            status=EvidenceStatus.APPROVED,
        )

    with pytest.raises(SprintTransitionConditionMissing):
        EvidenceService.approve_evidence_set(user=user, sprint=sprint)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.EVIDENCE_REVIEW


@pytest.mark.django_db
def test_cross_user_card_access_returns_404():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    other = get_user_model().objects.create_user(username="other@example.com")
    card = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Owned card",
        result="Result",
        source_excerpt="Experience leading product teams",
    )

    _other_user, other_sprint, _other_profile, _other_opportunity = (
        make_opportunity_confirmed_sprint("other-sprint@example.com")
    )
    other_sprint.user = other
    other_sprint.active_resume.user = other
    other_sprint.active_resume.save(update_fields=["user", "updated_at"])
    other_sprint.active_profile.user = other
    other_sprint.active_profile.save(update_fields=["user", "updated_at"])
    other_sprint.save(update_fields=["user", "updated_at"])

    with pytest.raises(Http404):
        EvidenceService.get_owned_card(user=other, sprint=other_sprint, card_id=card.id)


@pytest.mark.django_db
def test_unsupported_metric_requires_user_correction_before_approval():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    card = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Metric card",
        result="Result",
        metric="99%",
        source_excerpt="Experience leading product teams",
    )

    with pytest.raises(EvidenceError):
        EvidenceService.approve_card(user=user, sprint=sprint, card_id=card.id)

    EvidenceService.save_card(
        user=user,
        sprint=sprint,
        card_id=card.id,
        cleaned_data={
            "title": card.title,
            "problem": "",
            "role": "",
            "action": "",
            "result": "Result",
            "metric": "99%",
            "skills_text": [],
            "competencies_text": [],
            "ownership_signal": "",
            "constraints": "",
            "tradeoffs": "",
            "missing_details_text": [],
            "source_excerpt": card.source_excerpt,
            "source_location": "",
            "confidentiality": False,
        },
    )
    with pytest.raises(EvidenceError):
        EvidenceService.approve_card(user=user, sprint=sprint, card_id=card.id)

    EvidenceService.save_card(
        user=user,
        sprint=sprint,
        card_id=card.id,
        cleaned_data={
            "title": card.title,
            "problem": "",
            "role": "",
            "action": "",
            "result": "Result",
            "metric": "99%",
            "metric_user_corrected": True,
            "skills_text": [],
            "competencies_text": [],
            "ownership_signal": "",
            "constraints": "",
            "tradeoffs": "",
            "missing_details_text": [],
            "source_excerpt": card.source_excerpt,
            "source_location": "",
            "confidentiality": False,
        },
    )
    approved = EvidenceService.approve_card(user=user, sprint=sprint, card_id=card.id)

    assert approved.status == EvidenceStatus.APPROVED


@pytest.mark.django_db
def test_threshold_requires_valid_source_excerpt_provenance():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    valid_excerpt = "Experience leading product teams and delivering customer outcomes."
    for index in range(2):
        EvidenceCard.objects.create(
            user=user,
            profile=profile,
            source_document=sprint.active_resume,
            title=f"Valid evidence {index}",
            result="Clear result",
            source_excerpt=valid_excerpt,
            status=EvidenceStatus.APPROVED,
        )
    EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_document=sprint.active_resume,
        title="Invalid provenance",
        result="Clear result",
        source_excerpt="This excerpt is not in the resume.",
        status=EvidenceStatus.APPROVED,
    )

    threshold = EvidenceService.evaluate_threshold(user=user, sprint=sprint)

    assert not threshold.all_have_provenance
    assert not threshold.is_met
    with pytest.raises(SprintTransitionConditionMissing):
        EvidenceService.approve_evidence_set(user=user, sprint=sprint)


@pytest.mark.django_db
def test_highlight_edit_marks_approved_dependent_cards_stale():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    highlight = CareerHighlight.objects.create(
        user=user,
        profile=profile,
        title="Retention launch",
        description="Improved retention by building a lifecycle onboarding program.",
        metric="15%",
    )
    card = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_highlight=highlight,
        title="Retention evidence",
        result="Improved retention",
        metric="15%",
        source_excerpt="Improved retention by building a lifecycle onboarding program.",
        status=EvidenceStatus.APPROVED,
    )

    EvidenceService.update_highlight(
        user=user,
        sprint=sprint,
        highlight_id=highlight.id,
        cleaned_data={
            "title": "Retention launch updated",
            "description": "Changed upstream source text for this highlight.",
            "metric": None,
            "skills_text": [],
            "source_note": "",
        },
    )

    card.refresh_from_db()
    assert card.status == EvidenceStatus.STALE


@pytest.mark.django_db
def test_highlight_archive_marks_approved_dependent_cards_stale():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    highlight = CareerHighlight.objects.create(
        user=user,
        profile=profile,
        title="Activation launch",
        description="Improved activation by rebuilding onboarding for new users.",
    )
    card = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_highlight=highlight,
        title="Activation evidence",
        result="Improved activation",
        source_excerpt="Improved activation by rebuilding onboarding for new users.",
        status=EvidenceStatus.APPROVED,
    )

    EvidenceService.archive_highlight(user=user, sprint=sprint, highlight_id=highlight.id)

    card.refresh_from_db()
    assert card.status == EvidenceStatus.STALE


@pytest.mark.django_db
def test_archived_highlight_card_cannot_be_reapproved():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    highlight = CareerHighlight.objects.create(
        user=user,
        profile=profile,
        title="Expansion launch",
        description="Expanded onboarding to enterprise customers with measurable adoption.",
    )
    card = EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_highlight=highlight,
        title="Expansion evidence",
        result="Expanded adoption",
        source_excerpt="Expanded onboarding to enterprise customers with measurable adoption.",
        status=EvidenceStatus.APPROVED,
    )

    EvidenceService.archive_highlight(user=user, sprint=sprint, highlight_id=highlight.id)

    card.refresh_from_db()
    assert card.status == EvidenceStatus.STALE
    with pytest.raises(EvidenceError):
        EvidenceService.approve_card(user=user, sprint=sprint, card_id=card.id)
    card.refresh_from_db()
    assert card.status == EvidenceStatus.STALE


@pytest.mark.django_db
def test_threshold_rejects_approved_card_sourced_from_stale_highlight():
    user, sprint, profile, _opportunity = make_opportunity_confirmed_sprint()
    sprint.state = SprintState.EVIDENCE_REVIEW
    sprint.save(update_fields=["state", "updated_at"])
    active_excerpt = "Experience leading product teams and delivering customer outcomes."
    for index in range(2):
        EvidenceCard.objects.create(
            user=user,
            profile=profile,
            source_document=sprint.active_resume,
            title=f"Resume evidence {index}",
            result="Clear result",
            source_excerpt=active_excerpt,
            status=EvidenceStatus.APPROVED,
        )
    stale_highlight = CareerHighlight.objects.create(
        user=user,
        profile=profile,
        title="Archived source",
        description="Archived source text should not support approved evidence.",
        status=CareerHighlightStatus.STALE,
    )
    EvidenceCard.objects.create(
        user=user,
        profile=profile,
        source_highlight=stale_highlight,
        title="Stale source evidence",
        result="Clear result",
        source_excerpt="Archived source text should not support approved evidence.",
        status=EvidenceStatus.APPROVED,
    )

    threshold = EvidenceService.evaluate_threshold(user=user, sprint=sprint)

    assert not threshold.all_have_provenance
    assert not threshold.is_met
    with pytest.raises(SprintTransitionConditionMissing):
        EvidenceService.approve_evidence_set(user=user, sprint=sprint)
