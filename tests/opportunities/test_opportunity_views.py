from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from ai.schemas.jd import JDAnalysis
from apps.opportunities.models import CompanyContextStatus, Opportunity, OpportunityStatus
from apps.sprints.models import InterviewSprint, SprintState
from tests.ai.test_company_context_schema import valid_context
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
    assert opportunity.confirmation_status == OpportunityStatus.DRAFT
    assert sprint.state == SprintState.PROFILE_CONFIRMED

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/company-context/skip/")
    assert response.status_code == 302
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




@pytest.mark.django_db
def test_company_context_paste_then_confirm_flow(client):
    user, sprint, _profile = make_profile_confirmed_sprint(
        "context@example.com", password="password"
    )
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    client.login(username="context@example.com", password="password")

    with patch("apps.opportunities.services.EvidraAIService.extract_company_context") as extract:
        from ai.schemas.company_context import CompanyContext

        extract.return_value = CompanyContext.model_validate(valid_context())
        response = client.post(
            f"/workspace/opportunity/{opportunity.pk}/company-context/",
            data={
                "company_url": "",
                "pasted_company_context": "Example builds collaboration software.",
            },
        )

    assert response.status_code == 302
    opportunity.refresh_from_db()
    assert opportunity.company_context_status == CompanyContextStatus.PENDING_REVIEW
    assert opportunity.company_context["company_description"]

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/company-context/confirm/")
    assert response.status_code == 302
    opportunity.refresh_from_db()
    assert opportunity.company_context_status == CompanyContextStatus.CONFIRMED

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/confirm/")
    assert response.status_code == 302
    sprint.refresh_from_db()
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED


@pytest.mark.django_db
def test_company_context_url_submit_uses_fetcher_and_ai_without_live_network(client):
    _user, sprint, _profile = make_profile_confirmed_sprint(
        "url-context@example.com", password="password"
    )
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    client.login(username="url-context@example.com", password="password")

    from ai.schemas.company_context import CompanyContext
    from apps.opportunities.company_context import CompanyContextFetchResult

    fetch_result = CompanyContextFetchResult(
        final_url="https://example.com/about",
        visible_text="Example builds collaboration software for product teams.",
        content_type="text/html",
    )
    with (
        patch("apps.opportunities.services.CompanyContextFetcher") as fetcher_class,
        patch("apps.opportunities.services.EvidraAIService.extract_company_context") as extract,
    ):
        fetcher_class.return_value.fetch.return_value = fetch_result
        extract.return_value = CompanyContext.model_validate(valid_context())
        response = client.post(
            f"/workspace/opportunity/{opportunity.pk}/company-context/",
            data={"company_url": "https://example.com", "pasted_company_context": ""},
        )

    assert response.status_code == 302
    fetcher_class.return_value.fetch.assert_called_once_with("https://example.com")
    extract.assert_called_once()
    opportunity.refresh_from_db()
    assert opportunity.company_url == "https://example.com/about"
    assert opportunity.company_context_status == CompanyContextStatus.PENDING_REVIEW


@pytest.mark.django_db
def test_company_context_skip_allows_confirm_flow(client):
    _user, sprint, _profile = make_profile_confirmed_sprint("skip@example.com", password="password")
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    client.login(username="skip@example.com", password="password")

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/company-context/skip/")

    assert response.status_code == 302
    opportunity.refresh_from_db()
    assert opportunity.company_context_status == CompanyContextStatus.SKIPPED

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/confirm/")
    assert response.status_code == 302
    sprint.refresh_from_db()
    assert sprint.state == SprintState.OPPORTUNITY_CONFIRMED


@pytest.mark.django_db
def test_company_context_submit_rejects_cross_user_opportunity(client):
    _owner, sprint, _profile = make_profile_confirmed_sprint("ctx-owner@example.com")
    make_profile_confirmed_sprint("ctx-other@example.com", password="password")
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        **opportunity_data(),
    )
    client.login(username="ctx-other@example.com", password="password")

    response = client.post(
        f"/workspace/opportunity/{opportunity.pk}/company-context/skip/",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_company_context_review_edit_then_confirm_flow(client):
    _user, sprint, _profile = make_profile_confirmed_sprint(
        "edit-context@example.com", password="password"
    )
    opportunity = Opportunity.objects.create(
        sprint=sprint,
        jd_analysis=jd_analysis_dict(),
        company_context=valid_context(),
        company_context_status=CompanyContextStatus.PENDING_REVIEW,
        **opportunity_data(),
    )
    client.login(username="edit-context@example.com", password="password")

    response = client.post(
        f"/workspace/opportunity/{opportunity.pk}/company-context/review/",
        data={
            "company_description": "Example builds collaboration software for product teams.",
            "products_or_services": "Collaboration software",
            "target_users": "Product teams\nEngineering teams",
            "business_model_clues": "",
            "product_terminology": "workspace",
            "strategic_themes": "team productivity",
        },
    )

    assert response.status_code == 302
    opportunity.refresh_from_db()
    assert opportunity.company_context["target_users"] == ["Product teams", "Engineering teams"]
    assert opportunity.company_context_status == CompanyContextStatus.PENDING_REVIEW

    response = client.post(f"/workspace/opportunity/{opportunity.pk}/company-context/confirm/")
    assert response.status_code == 302
    opportunity.refresh_from_db()
    assert opportunity.company_context_status == CompanyContextStatus.CONFIRMED
