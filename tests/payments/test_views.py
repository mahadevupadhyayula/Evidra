from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import RazorpayPaymentService
from apps.sprints.models import SprintState
from tests.payments.helpers import PAYMENT_SETTINGS, FakeRazorpayClient, make_preview_ready_sprint


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_checkout_post_creates_order_and_shows_checkout_config(client):
    user, sprint = make_preview_ready_sprint()
    client.force_login(user)
    with patch.object(RazorpayPaymentService, "_client", return_value=FakeRazorpayClient()):
        response = client.post(reverse("payments:checkout"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "order_test" in content
    assert "rzp_test_key" in content
    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_status_page_filters_to_current_user_payment(client):
    user, sprint = make_preview_ready_sprint()
    other, other_sprint = make_preview_ready_sprint("other-payment@example.com")
    Payment.objects.create(
        user=other,
        sprint=other_sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_other",
        status=PaymentStatus.ORDER_CREATED,
    )
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_owner",
        status=PaymentStatus.ORDER_CREATED,
    )
    client.force_login(user)

    response = client.get(reverse("payments:status"))

    content = response.content.decode()
    assert "order_owner" in content
    assert "order_other" not in content


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_retry_after_failed_payment_creates_fresh_order(client):
    user, sprint = make_preview_ready_sprint()
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_failed",
        status=PaymentStatus.FAILED,
    )
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])
    client.force_login(user)
    with patch.object(
        RazorpayPaymentService, "_client", return_value=FakeRazorpayClient(order_id="order_retry")
    ):
        response = client.post(reverse("payments:retry"))

    assert response.status_code == 302
    assert Payment.objects.filter(
        user=user, sprint=sprint, provider_order_id="order_retry"
    ).exists()
    assert Payment.objects.filter(
        user=user, sprint=sprint, provider_order_id="order_failed"
    ).exists()


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_status_page_wires_polling_endpoint(client):
    user, sprint = make_preview_ready_sprint()
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_polling",
        status=PaymentStatus.ORDER_CREATED,
    )
    client.force_login(user)

    response = client.get(reverse("payments:status"))

    content = response.content.decode()
    assert 'hx-get="/workspace/payment/status/poll/"' in content
    assert 'hx-trigger="load, every 5s"' in content


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_status_page_prefers_paid_payment_over_newer_failed_payment(client):
    user, sprint = make_preview_ready_sprint()
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_paid_status",
        provider_payment_id="pay_paid_status",
        status=PaymentStatus.PAID,
    )
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_failed_status",
        status=PaymentStatus.FAILED,
    )
    client.force_login(user)

    response = client.get(reverse("payments:status"))

    content = response.content.decode()
    assert "Paid" in content
    assert "order_paid_status" in content
    assert "order_failed_status" not in content
