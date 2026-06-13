from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.documents.forms import ResumePasteForm, ResumeReviewForm, ResumeUploadForm
from apps.documents.models import DocumentParsingStatus
from apps.documents.services import ResumeConfirmationError, ResumeDocumentService
from apps.sprints.services import SprintWorkflowService


@login_required
def resume_upload(request):
    active_resume = ResumeDocumentService.get_active_resume(request.user)
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = ResumeDocumentService.create_from_upload(
                user=request.user,
                uploaded_file=form.cleaned_data["resume_file"],
            )
            if document.parsing_status == DocumentParsingStatus.PARSING_FAILED:
                messages.error(request, document.parsing_error)
                return redirect("documents:resume_paste")
            return redirect("documents:resume_review", document_id=document.pk)
    else:
        form = ResumeUploadForm()
    return render(
        request,
        "documents/upload.html",
        {"form": form, "active_resume": active_resume},
    )


@login_required
def resume_paste(request):
    if request.method == "POST":
        form = ResumePasteForm(request.POST)
        if form.is_valid():
            document = ResumeDocumentService.create_from_paste(
                user=request.user,
                text=form.cleaned_data["resume_text"],
            )
            return redirect("documents:resume_review", document_id=document.pk)
    else:
        form = ResumePasteForm()
    return render(request, "documents/paste.html", {"form": form})


@login_required
def resume_review(request, document_id):
    document = ResumeDocumentService.get_owned_document(request.user, document_id)
    if request.method == "POST":
        form = ResumeReviewForm(request.POST)
        if form.is_valid():
            try:
                document = ResumeDocumentService.update_review_text(
                    user=request.user,
                    document_id=document.pk,
                    cleaned_text=form.cleaned_data["cleaned_text"],
                )
                messages.success(request, "Resume text saved for review.")
                return redirect("documents:resume_review", document_id=document.pk)
            except ResumeConfirmationError as exc:
                form.add_error("cleaned_text", str(exc))
    else:
        form = ResumeReviewForm(initial={"cleaned_text": document.cleaned_text})
    return render(request, "documents/review.html", {"document": document, "form": form})


@login_required
@require_POST
def resume_confirm(request, document_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        ResumeDocumentService.confirm_resume(
            user=request.user,
            sprint=sprint,
            document_id=document_id,
        )
    except ResumeConfirmationError as exc:
        messages.error(request, str(exc))
        return redirect("documents:resume_review", document_id=document_id)
    messages.success(request, "Resume confirmed. Your Sprint is ready for profile review next.")
    return redirect("workspace:index")


@login_required
@require_POST
def resume_replace(request):
    messages.info(
        request,
        "Upload or paste a replacement resume. "
        "Your current resume stays active until you confirm the replacement.",
    )
    return redirect("documents:resume_upload")
