from django import forms

from apps.documents.services import (
    InvalidResumeFile,
    ResumeConfirmationError,
    ResumeDocumentService,
    ResumeParserService,
)


class ResumeUploadForm(forms.Form):
    resume_file = forms.FileField(label="PDF or DOCX resume")

    def clean_resume_file(self):
        uploaded_file = self.cleaned_data["resume_file"]
        try:
            ResumeParserService.validate_file(uploaded_file)
        except InvalidResumeFile as exc:
            raise forms.ValidationError(str(exc)) from exc
        return uploaded_file


class ResumePasteForm(forms.Form):
    resume_text = forms.CharField(label="Resume text", widget=forms.Textarea(attrs={"rows": 16}))

    def clean_resume_text(self) -> str:
        try:
            return ResumeDocumentService.normalize_resume_text(self.cleaned_data["resume_text"])
        except ResumeConfirmationError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ResumeReviewForm(forms.Form):
    cleaned_text = forms.CharField(
        label="Reviewed resume text",
        widget=forms.Textarea(attrs={"rows": 18}),
    )

    def clean_cleaned_text(self) -> str:
        try:
            return ResumeDocumentService.normalize_resume_text(self.cleaned_data["cleaned_text"])
        except ResumeConfirmationError as exc:
            raise forms.ValidationError(str(exc)) from exc
