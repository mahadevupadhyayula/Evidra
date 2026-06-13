from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from docx import Document as DocxDocument

from apps.documents.models import Document, DocumentParsingStatus
from apps.documents.services import (
    InvalidResumeFile,
    ResumeConfirmationError,
    ResumeDocumentService,
    ResumeParserService,
)
from apps.sprints.models import InterviewSprint, SprintState


def long_resume_text():
    return "Experience leading teams and delivering measurable product outcomes. " * 4


def pdf_upload(body=b"%PDF-1.4\nbody"):
    return SimpleUploadedFile("resume.pdf", body, content_type="application/pdf")


def docx_file():
    output = BytesIO()
    doc = DocxDocument()
    doc.add_paragraph(long_resume_text())
    doc.save(output)
    output.seek(0)
    return output


def test_validate_file_accepts_pdf():
    metadata = ResumeParserService.validate_file(pdf_upload())

    assert metadata.extension == ".pdf"
    assert metadata.mime_type == "application/pdf"


def test_validate_file_rejects_mismatched_mime_type():
    upload = SimpleUploadedFile("resume.pdf", b"%PDF-1.4", content_type="text/plain")

    with pytest.raises(InvalidResumeFile):
        ResumeParserService.validate_file(upload)


def test_extract_docx_text_reads_document_text():
    text = ResumeParserService.extract_docx_text(docx_file())

    assert "Experience leading teams" in text


def test_extract_pdf_text_requires_reviewable_text():
    page = SimpleNamespace(extract_text=lambda: long_resume_text())
    with patch("apps.documents.services.PdfReader", return_value=SimpleNamespace(pages=[page])):
        text = ResumeParserService.extract_pdf_text("/tmp/resume.pdf")

    assert "Experience leading teams" in text


def test_clean_text_normalizes_whitespace():
    assert ResumeParserService.clean_text(" A   B\n\n\nC ") == "A B\n\nC"


@pytest.mark.django_db
def test_create_from_paste_creates_reviewable_document():
    user = get_user_model().objects.create_user(username="user@example.com")

    document = ResumeDocumentService.create_from_paste(user=user, text=long_resume_text())

    assert document.user == user
    assert document.parsing_status == DocumentParsingStatus.READY_FOR_REVIEW
    assert document.cleaned_text
    assert not document.is_active


@pytest.mark.django_db
def test_create_from_upload_records_parsing_failure(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path
    user = get_user_model().objects.create_user(username="user@example.com")
    from apps.documents.services import ResumeParsingFailed

    with patch("apps.documents.services.ResumeParserService.extract_pdf_text") as extract:
        extract.side_effect = ResumeParsingFailed("parse failed")
        document = ResumeDocumentService.create_from_upload(user=user, uploaded_file=pdf_upload())

    assert document.parsing_status == DocumentParsingStatus.PARSING_FAILED
    assert document.parsing_error == "parse failed"
    assert not document.is_active


@pytest.mark.django_db
def test_confirm_resume_transitions_draft_to_resume_ready():
    user = get_user_model().objects.create_user(username="user@example.com")
    sprint = InterviewSprint.objects.create(user=user)
    document = Document.objects.create(
        user=user,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.READY_FOR_REVIEW,
    )

    ResumeDocumentService.confirm_resume(user=user, sprint=sprint, document_id=document.pk)

    document.refresh_from_db()
    sprint.refresh_from_db()
    assert document.is_active is True
    assert document.parsing_status == DocumentParsingStatus.CONFIRMED
    assert sprint.state == SprintState.RESUME_READY
    assert sprint.active_resume == document


@pytest.mark.django_db
def test_confirm_resume_rejects_cross_user_document():
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com")
    other = User.objects.create_user(username="other@example.com")
    sprint = InterviewSprint.objects.create(user=other)
    document = Document.objects.create(
        user=owner,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.READY_FOR_REVIEW,
    )

    with pytest.raises(Http404):
        ResumeDocumentService.confirm_resume(user=other, sprint=sprint, document_id=document.pk)

    document.refresh_from_db()
    assert not document.is_active


@pytest.mark.django_db
def test_confirm_resume_replaces_previous_active_resume_atomically():
    user = get_user_model().objects.create_user(username="user@example.com")
    old = Document.objects.create(
        user=user,
        cleaned_text=long_resume_text(),
        parsing_status=DocumentParsingStatus.CONFIRMED,
        is_active=True,
    )
    sprint = InterviewSprint.objects.create(
        user=user,
        state=SprintState.RESUME_READY,
        active_resume=old,
    )
    new = Document.objects.create(
        user=user,
        cleaned_text=long_resume_text() + " replacement",
        parsing_status=DocumentParsingStatus.READY_FOR_REVIEW,
    )

    ResumeDocumentService.confirm_resume(user=user, sprint=sprint, document_id=new.pk)

    old.refresh_from_db()
    new.refresh_from_db()
    sprint.refresh_from_db()
    assert old.is_active is False
    assert old.parsing_status == DocumentParsingStatus.REPLACED
    assert new.is_active is True
    assert sprint.state == SprintState.RESUME_READY
    assert sprint.active_resume == new


@pytest.mark.django_db
def test_confirm_resume_is_idempotent_for_active_confirmed_resume():
    user = get_user_model().objects.create_user(username="user@example.com")
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

    ResumeDocumentService.confirm_resume(user=user, sprint=sprint, document_id=document.pk)

    assert Document.objects.filter(user=user, is_active=True).count() == 1


@pytest.mark.django_db
def test_update_review_text_rejects_confirmed_active_resume_without_changing_sprint():
    user = get_user_model().objects.create_user(username="confirmed@example.com")
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

    with pytest.raises(ResumeConfirmationError):
        ResumeDocumentService.update_review_text(
            user=user,
            document_id=document.pk,
            cleaned_text=long_resume_text() + " edited",
        )

    document.refresh_from_db()
    sprint.refresh_from_db()
    assert document.is_active is True
    assert document.parsing_status == DocumentParsingStatus.CONFIRMED
    assert sprint.state == SprintState.RESUME_READY
    assert sprint.active_resume == document
