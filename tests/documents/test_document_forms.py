from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document as DocxDocument

from apps.documents.forms import ResumePasteForm, ResumeReviewForm, ResumeUploadForm


def pdf_upload(*, name="resume.pdf", content_type="application/pdf", body=None):
    return SimpleUploadedFile(name, body or b"%PDF-1.4\n%test", content_type=content_type)


def docx_bytes():
    output = BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("Experience " * 20)
    doc.save(output)
    return output.getvalue()


def test_upload_form_accepts_pdf():
    form = ResumeUploadForm(files={"resume_file": pdf_upload()})

    assert form.is_valid(), form.errors


def test_upload_form_accepts_docx():
    form = ResumeUploadForm(
        files={
            "resume_file": SimpleUploadedFile(
                "resume.docx",
                docx_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
    )

    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("name", "content_type", "body"),
    [
        ("resume.txt", "text/plain", b"hello"),
        ("resume.pdf", "text/plain", b"%PDF-1.4"),
        ("resume.pdf", "application/pdf", b"not a pdf"),
    ],
)
def test_upload_form_rejects_invalid_files(name, content_type, body):
    form = ResumeUploadForm(
        files={"resume_file": pdf_upload(name=name, content_type=content_type, body=body)}
    )

    assert not form.is_valid()
    assert "resume_file" in form.errors


def test_paste_form_normalizes_resume_text():
    form = ResumePasteForm(data={"resume_text": "  Experience   leading projects\n\n" * 8})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["resume_text"].startswith("Experience leading projects")


def test_paste_form_rejects_short_text():
    form = ResumePasteForm(data={"resume_text": "Too short"})

    assert not form.is_valid()
    assert "resume_text" in form.errors


def test_review_form_rejects_blank_text():
    form = ResumeReviewForm(data={"cleaned_text": "   "})

    assert not form.is_valid()
    assert "cleaned_text" in form.errors
