import pytest
from django.contrib.auth import get_user_model
from django.http import Http404

from ai.client import AIClientError, MockAIClient
from ai.services import AIJDAnalysisError, EvidraAIService
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.opportunities.services import OpportunityError, OpportunityService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import InvalidSprintTransition, SprintWorkflowService
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


@pytest.mark.django_db
def test_analyze_and_save_opportunity_creates_draft_with_analysis():
    user, sprint, _profile = make_profile_confirmed_sprint()
    client = MockAIClient(responses=[jd_analysis_dict()])

    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=client),
    )

    assert opportunity.sprint == sprint
    assert opportunity.confirmation_status == OpportunityStatus.DRAFT
    assert opportunity.jd_analysis["summary"]
    assert opportunity.role_family == "PRODUCT_MANAGEMENT"
    assert client.calls[0]["role_family"] == "PRODUCT_MANAGEMENT"
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_analyze_and_save_opportunity_updates_existing_draft():
    user, sprint, _profile = make_profile_confirmed_sprint()
    ai_service = EvidraAIService(
        client=MockAIClient(responses=[jd_analysis_dict(), jd_analysis_dict()])
    )

    first = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="First Title"),
        ai_service=ai_service,
    )
    second = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Second Title"),
        ai_service=ai_service,
    )

    assert first.pk == second.pk
    assert second.role_title == "Second Title"
    assert Opportunity.objects.filter(sprint=sprint).count() == 1


@pytest.mark.django_db
def test_analyze_rejects_sprint_before_profile_confirmed():
    user = get_user_model().objects.create_user(username="draft@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)

    with pytest.raises(InvalidSprintTransition):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(),
            ai_service=EvidraAIService(client=MockAIClient()),
        )


@pytest.mark.django_db
def test_ai_failure_preserves_draft_and_sprint_state():
    user, sprint, _profile = make_profile_confirmed_sprint()

    with pytest.raises(AIJDAnalysisError):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(role_title="Saved title"),
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("down"), AIClientError("down")])
            ),
        )

    opportunity = Opportunity.objects.get(sprint=sprint)
    assert opportunity.role_title == "Saved title"
    assert opportunity.jd_analysis is None
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_failed_reanalysis_clears_stale_analysis_and_blocks_confirmation():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(role_title="Original title"),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )
    assert opportunity.jd_analysis is not None

    with pytest.raises(AIJDAnalysisError):
        OpportunityService.analyze_and_save_opportunity(
            user=user,
            sprint=sprint,
            cleaned_data=opportunity_data(role_title="Updated title"),
            ai_service=EvidraAIService(
                client=MockAIClient(responses=[AIClientError("down"), AIClientError("down")])
            ),
        )

    opportunity.refresh_from_db()
    assert opportunity.role_title == "Updated title"
    assert opportunity.jd_analysis is None
    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user,
            sprint=sprint,
            opportunity_id=opportunity.pk,
        )
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_confirm_opportunity_transitions_sprint():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = OpportunityService.analyze_and_save_opportunity(
        user=user,
        sprint=sprint,
        cleaned_data=opportunity_data(),
        ai_service=EvidraAIService(client=MockAIClient(responses=[jd_analysis_dict()])),
    )

    OpportunityService.confirm_opportunity(user=user, sprint=sprint, opportunity_id=opportunity.pk)

    opportunity.refresh_from_db()
    sprint.refresh_from_db()
    assert opportunity.confirmation_status == OpportunityStatus.CONFIRMED
    assert opportunity.confirmed_at is not None
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED


@pytest.mark.django_db
def test_confirm_opportunity_rejects_missing_analysis():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    with pytest.raises(OpportunityError):
        OpportunityService.confirm_opportunity(
            user=user, sprint=sprint, opportunity_id=opportunity.pk
        )

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED


@pytest.mark.django_db
def test_get_owned_opportunity_rejects_cross_user_access():
    owner, sprint, _profile = make_profile_confirmed_sprint("owner@example.com")
    other = get_user_model().objects.create_user(username="other@example.com")
    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    assert opportunity.sprint.user == owner
    with pytest.raises(Http404):
        OpportunityService.get_owned_opportunity(other, opportunity.pk)


@pytest.mark.django_db
def test_mark_opportunity_confirmed_is_idempotent_for_confirmed_sprint():
    user, sprint, _profile = make_profile_confirmed_sprint()
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        confirmation_status=OpportunityStatus.CONFIRMED,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    SprintWorkflowService.mark_opportunity_confirmed(
        user=user, sprint=sprint, opportunity=opportunity
    )
    sprint.refresh_from_db()

    again = SprintWorkflowService.mark_opportunity_confirmed(
        user=user,
        sprint=sprint,
        opportunity=opportunity,
    )

    assert again.state == SprintState.OPPORTUNITY_CONFIRMED
