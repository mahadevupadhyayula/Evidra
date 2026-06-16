from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.practice.forms import PracticeAnswerForm
from apps.practice.services import PracticeError, PracticeService
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


def _context(user, sprint, form=None):
    context = PracticeService.practice_context(user=user, sprint=sprint)
    context["form"] = form or PracticeAnswerForm(questions=context["questions"])
    return context


@login_required
def practice_index(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    return render(request, "practice/index.html", _context(request.user, sprint))


@login_required
@require_POST
def practice_submit(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    context = PracticeService.practice_context(user=request.user, sprint=sprint)
    form = PracticeAnswerForm(request.POST, questions=context["questions"])
    if not form.is_valid():
        messages.error(request, "Please choose a current question and enter a text answer.")
        context["form"] = form
        return render(request, "practice/index.html", context)
    try:
        attempt = PracticeService.submit_answer(
            user=request.user,
            sprint=sprint,
            question_id=form.cleaned_data["question_id"],
            answer_text=form.cleaned_data["answer_text"],
        )
    except (
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
        PracticeError,
    ) as exc:
        messages.error(request, str(exc))
        context = PracticeService.practice_context(user=request.user, sprint=sprint)
        context["form"] = form
        return render(request, "practice/index.html", context)
    messages.success(request, f"Practice attempt #{attempt.attempt_number} saved.")
    return redirect("practice:index")


@login_required
@require_GET
def practice_history(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    attempts = PracticeService.attempt_history(
        user=request.user,
        sprint=sprint,
        question_id=request.GET.get("question_id") or None,
    )
    return render(request, "practice/_attempt_history.html", {"attempts": attempts})
