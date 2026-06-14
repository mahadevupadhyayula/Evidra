from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ai.services import AICompanyContextExtractionError, AIJDAnalysisError
from apps.opportunities.company_context import CompanyContextFetchError
from apps.opportunities.forms import (
    CompanyContextForm,
    CompanyContextReviewForm,
    OpportunityForm,
)
from apps.opportunities.services import OpportunityError, OpportunityService
from apps.sprints.models import SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


@login_required
def opportunity_detail(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    if sprint.state == SprintState.DRAFT:
        messages.error(request, "Confirm your resume before adding opportunity context.")
        return redirect("documents:resume_upload")
    if sprint.state == SprintState.RESUME_READY:
        messages.error(request, "Confirm your profile before adding opportunity context.")
        return redirect("profiles:profile_review")

    opportunity = OpportunityService.get_current_opportunity(user=request.user, sprint=sprint)
    if sprint.state == SprintState.PROFILE_CONFIRMED and (
        opportunity is None or not opportunity.jd_analysis or request.GET.get("edit") == "1"
    ):
        form = OpportunityForm(instance=opportunity)
        return render(
            request,
            "opportunities/form.html",
            {
                "form": form,
                "company_context_form": CompanyContextForm(),
                "opportunity": opportunity,
                "sprint": sprint,
            },
        )
    return render(
        request,
        "opportunities/review.html",
        {
            "opportunity": opportunity,
            "sprint": sprint,
            "company_context_form": CompanyContextForm(),
            "company_context_review_form": CompanyContextReviewForm.from_company_context(
                opportunity.company_context if opportunity else None
            ),
        },
    )


@login_required
@require_POST
def opportunity_analyze(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    existing = OpportunityService.get_current_opportunity(user=request.user, sprint=sprint)
    form = OpportunityForm(request.POST, instance=existing)
    if form.is_valid():
        try:
            OpportunityService.analyze_and_save_opportunity(
                user=request.user,
                sprint=sprint,
                cleaned_data=form.cleaned_data,
            )
        except (
            AIJDAnalysisError,
            InvalidSprintTransition,
            SprintTransitionConditionMissing,
        ) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Job description analyzed. Review before confirming.")
            return redirect("opportunities:opportunity_detail")
    return render(
        request,
        "opportunities/form.html",
        {
            "form": form,
            "company_context_form": CompanyContextForm(),
            "opportunity": existing,
            "sprint": sprint,
        },
    )


@login_required
@require_POST
def opportunity_confirm(request, opportunity_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        OpportunityService.confirm_opportunity(
            user=request.user,
            sprint=sprint,
            opportunity_id=opportunity_id,
        )
    except (OpportunityError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
        return redirect("opportunities:opportunity_detail")
    messages.success(
        request, "Opportunity confirmed. Your Sprint is ready for evidence review next."
    )
    return redirect("workspace:index")


@login_required
@require_POST
def company_context_submit(request, opportunity_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    form = CompanyContextForm(request.POST)
    if form.is_valid():
        try:
            if form.cleaned_data["company_url"]:
                OpportunityService.extract_company_context_from_url(
                    user=request.user,
                    sprint=sprint,
                    opportunity_id=opportunity_id,
                    company_url=form.cleaned_data["company_url"],
                )
            else:
                OpportunityService.extract_company_context_from_paste(
                    user=request.user,
                    sprint=sprint,
                    opportunity_id=opportunity_id,
                    pasted_company_context=form.cleaned_data["pasted_company_context"],
                )
        except (
            CompanyContextFetchError,
            AICompanyContextExtractionError,
            OpportunityError,
            InvalidSprintTransition,
            SprintTransitionConditionMissing,
        ) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Company context extracted. Review and confirm it.")
        return redirect("opportunities:opportunity_detail")

    opportunity = OpportunityService.get_current_opportunity(user=request.user, sprint=sprint)
    return render(
        request,
        "opportunities/review.html",
        {
            "opportunity": opportunity,
            "sprint": sprint,
            "company_context_form": form,
            "company_context_review_form": CompanyContextReviewForm.from_company_context(
                opportunity.company_context if opportunity else None
            ),
        },
    )


@login_required
@require_POST
def company_context_review(request, opportunity_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    opportunity = OpportunityService.get_owned_opportunity(request.user, opportunity_id)
    form = CompanyContextReviewForm(request.POST)
    if form.is_valid():
        try:
            OpportunityService.update_company_context_review(
                user=request.user,
                sprint=sprint,
                opportunity_id=opportunity_id,
                company_context_payload=form.cleaned_data["company_context_payload"],
            )
        except (OpportunityError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Company context edits saved. Review before confirming.")
        return redirect("opportunities:opportunity_detail")

    return render(
        request,
        "opportunities/review.html",
        {
            "opportunity": opportunity,
            "sprint": sprint,
            "company_context_form": CompanyContextForm(),
            "company_context_review_form": form,
        },
    )


@login_required
@require_POST
def company_context_confirm(request, opportunity_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        OpportunityService.confirm_company_context(
            user=request.user, sprint=sprint, opportunity_id=opportunity_id
        )
    except (OpportunityError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Company context confirmed.")
    return redirect("opportunities:opportunity_detail")


@login_required
@require_POST
def company_context_skip(request, opportunity_id):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        OpportunityService.skip_company_context(
            user=request.user, sprint=sprint, opportunity_id=opportunity_id
        )
    except (OpportunityError, InvalidSprintTransition, SprintTransitionConditionMissing) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Continuing without company context.")
    return redirect("opportunities:opportunity_detail")
