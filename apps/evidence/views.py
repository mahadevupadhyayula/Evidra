from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AIEvidenceExtractionError
from apps.evidence.forms import CareerHighlightForm, EvidenceCardForm
from apps.evidence.services import EvidenceError, EvidenceService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def _review_context(request, sprint, *, highlight_form=None, card_form=None, editing_card=None):
    cards = EvidenceService.list_cards(user=request.user, sprint=sprint)
    highlights = EvidenceService.list_highlights(user=request.user, sprint=sprint)
    threshold = EvidenceService.evaluate_threshold(user=request.user, sprint=sprint)
    return {
        "sprint": sprint,
        "highlights": highlights,
        "cards": cards,
        "threshold": threshold,
        "highlight_form": highlight_form or CareerHighlightForm(),
        "card_form": card_form,
        "editing_card": editing_card,
    }


@login_required
def evidence_review(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    if sprint.state in {SprintState.DRAFT, SprintState.RESUME_READY}:
        messages.error(request, "Confirm your resume and profile before evidence review.")
        return redirect("workspace:index")
    if sprint.state == SprintState.PROFILE_CONFIRMED:
        messages.error(request, "Confirm your opportunity before evidence review.")
        return redirect("opportunities:opportunity_detail")
    try:
        context = _review_context(request, sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("workspace:index")
    return render(request, "evidence/review.html", context)


@login_required
@require_POST
def highlight_add(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    form = CareerHighlightForm(request.POST)
    if form.is_valid():
        try:
            EvidenceService.create_highlight(
                user=request.user,
                sprint=sprint,
                cleaned_data=form.cleaned_data,
            )
        except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Career highlight added for evidence review.")
            return redirect("evidence:evidence_review")
    return render(
        request,
        "evidence/review.html",
        _review_context(request, sprint, highlight_form=form),
    )


@login_required
@require_POST
def highlight_edit(request, highlight_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    highlight = EvidenceService.get_owned_highlight(
        user=request.user, sprint=sprint, highlight_id=highlight_id
    )
    form = CareerHighlightForm(request.POST, instance=highlight)
    if form.is_valid():
        try:
            EvidenceService.update_highlight(
                user=request.user,
                sprint=sprint,
                highlight_id=highlight_id,
                cleaned_data=form.cleaned_data,
            )
        except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Career highlight updated.")
    return redirect("evidence:evidence_review")


@login_required
@require_POST
def highlight_archive(request, highlight_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        EvidenceService.archive_highlight(
            user=request.user,
            sprint=sprint,
            highlight_id=highlight_id,
        )
    except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Career highlight removed from active evidence review.")
    return redirect("evidence:evidence_review")


@login_required
@require_POST
def evidence_extract(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        count = EvidenceService.extract_evidence(user=request.user, sprint=sprint)
    except (
        AIEvidenceExtractionError,
        EvidenceError,
        InvalidSprintTransition,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Evidence extraction complete. {count} new card(s) added.")
    return redirect("evidence:evidence_review")


@login_required
@require_POST
def card_save(request, card_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    card = EvidenceService.get_owned_card(user=request.user, sprint=sprint, card_id=card_id)
    form = EvidenceCardForm(request.POST, instance=card)
    if form.is_valid():
        try:
            EvidenceService.save_card(
                user=request.user,
                sprint=sprint,
                card_id=card_id,
                cleaned_data=form.cleaned_data,
            )
        except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Evidence card saved.")
            return redirect("evidence:evidence_review")
    return render(
        request,
        "evidence/review.html",
        _review_context(request, sprint, card_form=form, editing_card=card),
    )


@login_required
@require_POST
def card_approve(request, card_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        EvidenceService.approve_card(
            user=request.user,
            sprint=sprint,
            card_id=card_id,
        )
    except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Evidence card approved.")
    return redirect("evidence:evidence_review")


@login_required
@require_POST
def card_reject(request, card_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        EvidenceService.reject_card(user=request.user, sprint=sprint, card_id=card_id)
    except (EvidenceError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Evidence card rejected.")
    return redirect("evidence:evidence_review")


@login_required
@require_POST
def evidence_continue(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        EvidenceService.approve_evidence_set(user=request.user, sprint=sprint)
    except (InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Evidence threshold met. Evidence is approved for future stories.",
        )
    return redirect("workspace:index")
