import pytest
from django.urls import reverse

from apps.payments.models import PaymentStatus
from apps.payments.services import RazorpayPaymentService
from apps.sprints.models import SprintState
from tests.payments.helpers import (
    PAYMENT_SETTINGS,
    FakeRazorpayClient,
    make_preview_ready_sprint,
    sign,
    webhook_body,
)


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_endpoint_marks_paid(client):
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id)

    response = client.post(
        reverse("payments:razorpay_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sign(body),
    )

    assert response.status_code == 200
    payment.refresh_from_db()
    sprint.refresh_from_db()
    assert payment.status == PaymentStatus.PAID
    assert sprint.state == SprintState.PAID


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_endpoint_rejects_invalid_signature(client):
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id)

    response = client.post(
        reverse("payments:razorpay_webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="bad",
    )

    assert response.status_code == 400
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED
