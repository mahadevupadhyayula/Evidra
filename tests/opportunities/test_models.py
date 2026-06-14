import pytest
from django.db import IntegrityError

from apps.opportunities.models import Opportunity, OpportunityStatus
from tests.opportunities.helpers import make_profile_confirmed_sprint, opportunity_data


@pytest.mark.django_db
def test_opportunity_inherits_ownership_from_sprint():
    user, sprint, _profile = make_profile_confirmed_sprint()

    opportunity = Opportunity.objects.create(sprint=sprint, **opportunity_data())

    assert opportunity.sprint.user == user
    assert opportunity.confirmation_status == OpportunityStatus.DRAFT


@pytest.mark.django_db
def test_database_prevents_duplicate_current_opportunity_for_sprint():
    _user, sprint, _profile = make_profile_confirmed_sprint()
    Opportunity.objects.create(sprint=sprint, **opportunity_data())

    with pytest.raises(IntegrityError):
        Opportunity.objects.create(sprint=sprint, **opportunity_data(role_title="Other"))


@pytest.mark.django_db
def test_database_allows_stale_plus_current_opportunity():
    _user, sprint, _profile = make_profile_confirmed_sprint()
    Opportunity.objects.create(
        sprint=sprint,
        confirmation_status=OpportunityStatus.STALE,
        **opportunity_data(),
    )

    current = Opportunity.objects.create(sprint=sprint, **opportunity_data(role_title="Other"))

    assert current.confirmation_status == OpportunityStatus.DRAFT
