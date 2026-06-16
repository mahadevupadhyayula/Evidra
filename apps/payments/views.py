from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.payments.forms import PaymentRetryForm, PaymentStartForm
from apps.payments.services import (
    PaymentConfigurationError,
    PaymentProcessingError,
    RazorpayPaymentService,
)
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


@login_required
def payment_checkout(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    service = RazorpayPaymentService()
    if request.method == "POST":
        form = PaymentStartForm(request.POST)
        if form.is_valid():
            try:
                context = service.checkout_context(user=request.user, sprint=sprint)
            except (
                PaymentConfigurationError,
                PaymentProcessingError,
                InvalidSprintTransition,
                SprintOwnershipError,
                SprintTransitionConditionMissing,
            ) as exc:
                messages.error(request, str(exc))
                return redirect("previews:detail")
            messages.success(request, "Created your secure Razorpay checkout order.")
            return render(request, "payments/checkout.html", {"sprint": sprint, **context})
    else:
        form = PaymentStartForm()
    payment = service.current_payment(user=request.user, sprint=sprint)
    return render(
        request,
        "payments/checkout.html",
        {"sprint": sprint, "form": form, "payment": payment},
    )


@login_required
def payment_status(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    payment = RazorpayPaymentService.current_payment(user=request.user, sprint=sprint)
    return render(request, "payments/status.html", {"sprint": sprint, "payment": payment})


@login_required
def payment_status_poll(request):
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    payment = RazorpayPaymentService.current_payment(user=request.user, sprint=sprint)
    return render(request, "payments/_status_card.html", {"sprint": sprint, "payment": payment})


@login_required
@require_POST
def payment_retry(request):
    form = PaymentRetryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not retry payment. Please reload and try again.")
        return redirect("payments:status")
    sprint = SprintWorkflowService.get_or_create_current_sprint(request.user)
    try:
        RazorpayPaymentService().retry_payment(user=request.user, sprint=sprint)
    except (
        PaymentConfigurationError,
        PaymentProcessingError,
        InvalidSprintTransition,
        SprintOwnershipError,
        SprintTransitionConditionMissing,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Created a fresh Razorpay order. Continue checkout when ready.")
    return redirect("payments:checkout")


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        RazorpayPaymentService().process_webhook(raw_body=request.body, signature=signature)
    except (PaymentConfigurationError, PaymentProcessingError):
        return HttpResponseBadRequest("invalid webhook")
    return HttpResponse("ok")
