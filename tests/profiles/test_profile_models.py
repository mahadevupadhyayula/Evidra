import pytest
from django.contrib.auth import get_user_model

from apps.documents.models import Document, DocumentParsingStatus
from apps.profiles.models import CareerProfile, CareerProfileStatus


@pytest.mark.django_db
def test_profile_defaults_and_relationships():
    user = get_user_model().objects.create_user(username="user@example.com")
    document = Document.objects.create(
        user=user,
        cleaned_text="Experience building products. " * 10,
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )

    profile = CareerProfile.objects.create(user=user, active_resume=document)

    assert profile.confirmation_status == CareerProfileStatus.DRAFT
    assert profile.industries == []
    assert profile.skills == []
    assert profile.confirmed_at is None
    assert profile.active_resume == document
