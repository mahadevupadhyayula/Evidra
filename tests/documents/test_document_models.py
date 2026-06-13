import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.documents.models import Document, DocumentParsingStatus, DocumentType


@pytest.mark.django_db
def test_document_defaults_to_resume_upload_state():
    user = get_user_model().objects.create_user(username="user@example.com")

    document = Document.objects.create(user=user)

    assert document.document_type == DocumentType.RESUME
    assert document.parsing_status == DocumentParsingStatus.UPLOADED
    assert document.is_active is False


def test_document_statuses_match_resume_scope():
    assert [status.value for status in DocumentParsingStatus] == [
        "UPLOADED",
        "VALIDATING",
        "PARSING",
        "READY_FOR_REVIEW",
        "CONFIRMED",
        "INVALID_FILE",
        "PARSING_FAILED",
        "REPLACED",
    ]


@pytest.mark.django_db
def test_database_prevents_multiple_active_resumes_per_user():
    user = get_user_model().objects.create_user(username="user@example.com")
    Document.objects.create(user=user, is_active=True)

    with pytest.raises(IntegrityError):
        Document.objects.create(user=user, is_active=True)


@pytest.mark.django_db
def test_different_users_can_each_have_active_resume():
    User = get_user_model()
    user_a = User.objects.create_user(username="a@example.com")
    user_b = User.objects.create_user(username="b@example.com")

    Document.objects.create(user=user_a, is_active=True)
    Document.objects.create(user=user_b, is_active=True)

    assert Document.objects.filter(is_active=True).count() == 2
