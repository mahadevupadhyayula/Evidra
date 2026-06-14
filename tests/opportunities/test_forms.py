import pytest

from apps.opportunities.forms import OpportunityForm
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
