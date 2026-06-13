from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.documents.models import Document, DocumentParsingStatus
from apps.documents.services import ResumeParsingFailed
from apps.sprints.models import InterviewSprint, SprintState


def long_resume_text():
    return "Experience leading teams and delivering measurable product outcomes. " * 4


@pytest.mark.django_db
def test_resume_upload_requires_authentication(client):
    response = client.get(reverse("documents:resume_upload"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_paste_resume_review_and_confirm_flow(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)

    paste_response = client.post(
        reverse("documents:resume_paste"),
        {"resume_text": long_resume_text()},
    )

    document = Document.objects.get(user=user)
    assert paste_response.status_code == 302
    assert paste_response.url == reverse("documents:resume_review", args=[document.pk])
    assert document.parsing_status == DocumentParsingStatus.READY_FOR_REVIEW

    review_response = client.post(
        reverse("documents:resume_review", args=[document.pk]),
        {"cleaned_text": long_resume_text() + " corrected"},
    )
    assert review_response.status_code == 302
    document.refresh_from_db()
    assert "corrected" in document.cleaned_text

    confirm_response = client.post(reverse("documents:resume_confirm", args=[document.pk]))

    sprint = InterviewSprint.objects.get(user=user)
    document.refresh_from_db()
    assert confirm_response.status_code == 302
    assert confirm_response.url == reverse("workspace:index")
    assert document.is_active
    assert document.parsing_status == DocumentParsingStatus.CONFIRMED
    assert sprint.state == SprintState.RESUME_READY


@pytest.mark.django_db
def test_review_rejects_cross_user_access(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    viewer = User.objects.create_user(username="viewer@example.com")
    document = Document.objects.create(
        user=owner,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.READY_FOR_REVIEW,
    )
    client.force_login(viewer)

    response = client.get(reverse("documents:resume_review", args=[document.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_confirm_rejects_cross_user_access(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    viewer = User.objects.create_user(username="viewer@example.com")
    document = Document.objects.create(
        user=owner,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.READY_FOR_REVIEW,
    )
    client.force_login(viewer)

    response = client.post(reverse("documents:resume_confirm", args=[document.pk]))

    assert response.status_code == 404
    document.refresh_from_db()
    assert not document.is_active


@pytest.mark.django_db
def test_upload_parser_failure_redirects_to_paste_fallback(client, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    user = get_user_model().objects.create_user(username="user@example.com")
    client.force_login(user)
    upload = SimpleUploadedFile("resume.pdf", b"%PDF-1.4\nbody", content_type="application/pdf")

    with patch("apps.documents.services.ResumeParserService.extract_pdf_text") as extract:
        extract.side_effect = ResumeParsingFailed("parse failed")
        response = client.post(reverse("documents:resume_upload"), {"resume_file": upload})

    assert response.status_code == 302
    assert response.url == reverse("documents:resume_paste")
    document = Document.objects.get(user=user)
    assert document.parsing_status == DocumentParsingStatus.PARSING_FAILED


@pytest.mark.django_db
def test_replace_resume_keeps_current_active_until_new_confirmed(client):
    user = get_user_model().objects.create_user(username="user@example.com")
    old = Document.objects.create(
        user=user,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )
    InterviewSprint.objects.create(user=user, state=SprintState.RESUME_READY, active_resume=old)
    client.force_login(user)

    response = client.post(reverse("documents:resume_replace"))

    assert response.status_code == 302
    old.refresh_from_db()
    assert old.is_active
    assert old.parsing_status == DocumentParsingStatus.CONFIRMED


@pytest.mark.django_db
def test_upload_success_redirects_to_review(client, settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    user = get_user_model().objects.create_user(username="upload@example.com")
    client.force_login(user)
    upload = SimpleUploadedFile("resume.pdf", b"%PDF-1.4\nbody", content_type="application/pdf")

    with patch("apps.documents.services.ResumeParserService.extract_pdf_text") as extract:
        extract.return_value = long_resume_text()
        response = client.post(reverse("documents:resume_upload"), {"resume_file": upload})

    document = Document.objects.get(user=user)
    assert response.status_code == 302
    assert response.url == reverse("documents:resume_review", args=[document.pk])
    assert document.parsing_status == DocumentParsingStatus.READY_FOR_REVIEW
    assert document.storage_key.startswith(f"resumes/user-{user.id}/")


@pytest.mark.django_db
def test_review_post_cannot_make_confirmed_active_resume_unconfirmed(client):
    user = get_user_model().objects.create_user(username="confirmed-view@example.com")
    document = Document.objects.create(
        user=user,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )
    sprint = InterviewSprint.objects.create(
        user=user,
        state=SprintState.RESUME_READY,
        active_resume=document,
    )
    client.force_login(user)

    response = client.post(
        reverse("documents:resume_review", args=[document.pk]),
        {"cleaned_text": long_resume_text() + " edited"},
    )

    document.refresh_from_db()
    sprint.refresh_from_db()
    assert response.status_code == 200
    assert document.is_active is True
    assert document.parsing_status == DocumentParsingStatus.CONFIRMED
    assert sprint.state == SprintState.RESUME_READY
    assert sprint.active_resume == document
