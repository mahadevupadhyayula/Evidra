from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from ai.schemas.jd import JDAnalysis
from apps.opportunities.models import Opportunity, OpportunityStatus
from apps.sprints.models import InterviewSprint, SprintState
from tests.opportunities.helpers import (
    jd_analysis_dict,
    make_profile_confirmed_sprint,
    opportunity_data,
)


@pytest.mark.django_db
def test_opportunity_detail_requires_login(client):
    response = client.get("/workspace/opportunity/")

    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_opportunity_detail_redirects_before_profile_confirmed(client):
    user = get_user_model().objects.create_user(username="draft@example.com", password="password")
    InterviewSprint.objects.create(user=user, state=SprintState.DRAFT)
    client.login(username="draft@example.com", password="password")

    response = client.get("/workspace/opportunity/")

    assert response.status_code == 302
    assert response["Location"] == "/workspace/resume/upload/"


@pytest.mark.django_db
def test_profile_confirmed_user_can_view_opportunity_form(client):
    _user, _sprint, _profile = make_profile_confirmed_sprint(
        "form@example.com",
        password="password",
    )
    client.login(username="form@example.com", password="password")

    response = client.get("/workspace/opportunity/")

    assert response.status_code == 200
    assert b"Add your target role" in response.content


@pytest.mark.django_db
def test_opportunity_analyze_then_confirm_flow(client):
    user, sprint, _profile = make_profile_confirmed_sprint("flow@example.com", password="password")
    client.login(username="flow@example.com", password="password")

    with patch("apps.opportunities.services.EvidraAIService.analyze_jd") as analyze_jd:
        analyze_jd.return_value = JDAnalysis.model_validate(jd_analysis_dict())
        response = client.post("/workspace/opportunity/analyze/", data=opportunity_data())

    assert response.status_code == 302
    opportunity = Opportunity.objects.get(sprint=sprint)
    assert opportunity.jd_analysis["summary"]
    analyze_jd.assert_called_once()
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PROFILE_CONFIRMED

    response = client.get("/workspace/opportunity/")
    assert response.status_code == 200
    assert b"Review your opportunity context" in response.content

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/confirm/")
    assert response.status_code == 302
    opportunity.refresh_from_db()
    sprint.refresh_from_db()
    assert opportunity.confirmation_status == OpportunityStatus.CONFIRMED
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED
    assert InterviewSprint.objects.get(user=user).state == SprintState.OPPORTUNITY_CONFIRMED


@pytest.mark.django_db
def test_invalid_opportunity_form_does_not_call_ai(client):
    make_profile_confirmed_sprint("invalid@example.com", password="password")
    client.login(username="invalid@example.com", password="password")

    with patch("apps.opportunities.services.EvidraAIService.analyze_jd") as analyze_jd:
        response = client.post(
            "/workspace/opportunity/analyze/",
            data=opportunity_data(job_description="short"),
        )

    assert response.status_code == 200
    analyze_jd.assert_not_called()


@pytest.mark.django_db
def test_opportunity_confirm_rejects_cross_user_opportunity(client):
    _owner, sprint, _profile = make_profile_confirmed_sprint("owner@example.com")
    make_profile_confirmed_sprint("other@example.com", password="password")
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    client.login(username="other@example.com", password="password")

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/confirm/")

    assert response.status_code == 404
