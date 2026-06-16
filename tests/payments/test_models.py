import pytest
from django.contrib.auth import get_user_model

from apps.payments.models import Payment, PaymentStatus
from apps.sprints.models import InterviewSprint


@pytest.mark.django_db
def test_payment_status_values_match_stage_scope():
    assert [choice.value for choice in PaymentStatus] == [
        "NOT_STARTED",
        "ORDER_CREATED",
        "PAYMENT_PENDING",
        "PAID",
        "FAILED",
        "REFUNDED",
    ]


@pytest.mark.django_db
def test_payment_is_directly_user_owned_and_linked_to_sprint():
    user = get_user_model().objects.create_user(username="owner@example.com")
    sprint = InterviewSprint.objects.create(user=user)
    payment = Payment.objects.create(user=user, sprint=sprint, amount=499900, currency="INR")

    assert payment.user == user
    assert payment.sprint == sprint
    assert payment.provider == Payment.PROVIDER_RAZORPAY
