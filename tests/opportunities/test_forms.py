import pytest

from apps.opportunities.forms import CompanyContextForm, OpportunityForm
from tests.opportunities.helpers import opportunity_data


@pytest.mark.django_db
def test_opportunity_form_accepts_stage_fields():
    form = OpportunityForm(data=opportunity_data())

    assert form.is_valid(), form.errors
    assert form.cleaned_data["role_title"] == "Senior Product Manager"


@pytest.mark.django_db
def test_opportunity_form_rejects_short_jd():
    form = OpportunityForm(data=opportunity_data(job_description="too short"))

    assert not form.is_valid()
    assert "job_description" in form.errors


@pytest.mark.django_db
def test_opportunity_form_rejects_invalid_role_family():
    form = OpportunityForm(data=opportunity_data(role_family="NOT_A_ROLE"))

    assert not form.is_valid()
    assert "role_family" in form.errors


def test_company_context_form_accepts_url_only():
    form = CompanyContextForm(
        data={"company_url": "https://example.com", "pasted_company_context": ""}
    )

    assert form.is_valid()


def test_company_context_form_accepts_paste_only():
    form = CompanyContextForm(
        data={"company_url": "", "pasted_company_context": "Example builds collaboration software."}
    )

    assert form.is_valid()


def test_company_context_form_rejects_url_and_paste_together():
    form = CompanyContextForm(
        data={"company_url": "https://example.com", "pasted_company_context": "Example text"}
    )

    assert not form.is_valid()
    assert "__all__" in form.errors


def test_company_context_form_requires_url_paste_or_skip():
    form = CompanyContextForm(data={"company_url": "", "pasted_company_context": ""})

    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_opportunity_form_does_not_accept_company_url_field():
    data = opportunity_data(company_url="http://127.0.0.1/")
    form = OpportunityForm(data=data)

    assert form.is_valid(), form.errors
    assert "company_url" not in form.cleaned_data


def test_company_context_form_rejects_unsupported_url_scheme():
    form = CompanyContextForm(
        data={"company_url": "ftp://example.com", "pasted_company_context": ""}
    )

    assert not form.is_valid()
    assert "company_url" in form.errors


def test_company_context_review_form_accepts_edited_context():
    from apps.opportunities.forms import CompanyContextReviewForm

    form = CompanyContextReviewForm(
        data={
            "company_description": "Example builds collaboration software.",
            "products_or_services": "Collaboration software\nWorkflow tools",
            "target_users": "Product teams",
            "business_model_clues": "",
            "product_terminology": "workspace, roadmap",
            "strategic_themes": "team productivity",
        }
    )

    assert form.is_valid(), form.errors
    payload = form.cleaned_data["company_context_payload"]
    assert payload["products_or_services"] == ["Collaboration software", "Workflow tools"]
    assert payload["product_terminology"] == ["workspace", "roadmap"]


def test_company_context_review_form_rejects_empty_context():
    from apps.opportunities.forms import CompanyContextReviewForm

    form = CompanyContextReviewForm(
        data={
            "company_description": "",
            "products_or_services": "",
            "target_users": "",
            "business_model_clues": "",
            "product_terminology": "",
            "strategic_themes": "",
        }
    )

    assert not form.is_valid()
    assert "__all__" in form.errors
