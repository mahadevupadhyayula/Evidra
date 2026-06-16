import json

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import PaymentProcessingError, RazorpayPaymentService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)
from tests.payments.helpers import (
    PAYMENT_SETTINGS,
    FakeRazorpayClient,
    make_preview_ready_sprint,
    sign,
    webhook_body,
)


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_create_order_moves_preview_ready_to_payment_pending():
    user, sprint = make_preview_ready_sprint()
    client = FakeRazorpayClient()

    payment = RazorpayPaymentService(client=client).create_or_reuse_order(user=user, sprint=sprint)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING
    assert payment.status == PaymentStatus.ORDER_CREATED
    assert payment.provider_order_id == "order_test"
    assert client.created_payloads[0]["amount"] == 499900


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_create_order_reuses_active_order_without_provider_call():
    user, sprint = make_preview_ready_sprint()
    payment = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_existing",
        status=PaymentStatus.ORDER_CREATED,
    )
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])
    client = FakeRazorpayClient(order_id="order_new")

    reused = RazorpayPaymentService(client=client).create_or_reuse_order(user=user, sprint=sprint)

    assert reused == payment
    assert client.created_payloads == []


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_create_order_rejects_before_preview_ready():
    user = get_user_model().objects.create_user(username="early@example.com")
    sprint = InterviewSprint.objects.create(user=user, state=SprintState.MATCHING_READY)

    with pytest.raises(InvalidSprintTransition):
        RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
            user=user, sprint=sprint
        )


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_success_webhook_marks_payment_and_sprint_paid():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id)

    result = RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    payment.refresh_from_db()
    sprint.refresh_from_db()
    assert result.processed is True
    assert payment.status == PaymentStatus.PAID
    assert payment.provider_payment_id == "pay_test"
    assert payment.paid_at is not None
    assert sprint.state == SprintState.PAID


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_rejects_invalid_signature_and_preserves_state():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id)

    with pytest.raises(PaymentProcessingError):
        RazorpayPaymentService().process_webhook(raw_body=body, signature="bad")

    payment.refresh_from_db()
    sprint.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED
    assert sprint.state == SprintState.PAYMENT_PENDING


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_rejects_amount_mismatch():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id, amount=1)

    with pytest.raises(PaymentProcessingError):
        RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_duplicate_event_is_idempotent():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    payment.status = PaymentStatus.PAID
    payment.provider_payment_id = "pay_test"
    payment.webhook_event_id = "evt_test"
    payment.paid_at = timezone.now()
    payment.save()
    body = webhook_body(order_id=payment.provider_order_id)

    result = RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    assert result.duplicate is True


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_failed_webhook_preserves_sprint_for_retry():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(event="payment.failed", order_id=payment.provider_order_id)

    RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    payment.refresh_from_db()
    sprint.refresh_from_db()
    assert payment.status == PaymentStatus.FAILED
    assert sprint.state == SprintState.PAYMENT_PENDING


@pytest.mark.django_db
def test_mark_paid_requires_verified_paid_payment():
    user, sprint = make_preview_ready_sprint()
    payment = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_test",
        status=PaymentStatus.ORDER_CREATED,
    )
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_paid(user=user, sprint=sprint, payment=payment)

@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_mark_payment_pending_requires_expected_amount_and_currency():
    user, sprint = make_preview_ready_sprint()
    payment = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=1,
        currency="USD",
        provider_order_id="order_wrong_terms",
        status=PaymentStatus.ORDER_CREATED,
    )

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_payment_pending(user=user, sprint=sprint, payment=payment)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PREVIEW_READY


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_mark_paid_requires_order_and_expected_terms():
    user, sprint = make_preview_ready_sprint()
    payment = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=1,
        currency="USD",
        status=PaymentStatus.PAID,
        provider_payment_id="pay_wrong_terms",
        paid_at=timezone.now(),
    )
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_paid(user=user, sprint=sprint, payment=payment)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_failed_webhook_after_paid_does_not_downgrade_payment_or_sprint():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    success_body = webhook_body(order_id=payment.provider_order_id)
    RazorpayPaymentService().process_webhook(
        raw_body=success_body, signature=sign(success_body)
    )
    failed_body = webhook_body(
        event="payment.failed",
        event_id="evt_failed_after_paid",
        order_id=payment.provider_order_id,
        payment_id="pay_failed_after_paid",
    )

    result = RazorpayPaymentService().process_webhook(
        raw_body=failed_body, signature=sign(failed_body)
    )

    payment.refresh_from_db()
    sprint.refresh_from_db()
    assert result.message == "ignored_paid"
    assert payment.status == PaymentStatus.PAID
    assert payment.provider_payment_id == "pay_test"
    assert sprint.state == SprintState.PAID


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_mark_paid_rejects_wrong_amount_even_with_verified_payment_fields():
    user, sprint = make_preview_ready_sprint()
    payment = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=1,
        currency="INR",
        status=PaymentStatus.PAID,
        provider_order_id="order_wrong_amount",
        provider_payment_id="pay_wrong_amount",
        paid_at=timezone.now(),
    )
    sprint.state = SprintState.PAYMENT_PENDING
    sprint.save(update_fields=["state", "updated_at"])

    with pytest.raises(SprintTransitionConditionMissing):
        SprintWorkflowService.mark_paid(user=user, sprint=sprint, payment=payment)

    sprint.refresh_from_db()
    assert sprint.state == SprintState.PAYMENT_PENDING


def _webhook_body_with_entity(entity, *, event="payment.captured", event_id="evt_custom"):
    return json.dumps(
        {"id": event_id, "event": event, "payload": {"payment": {"entity": entity}}},
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_current_payment_prefers_paid_payment_over_newer_failed_payment():
    user, sprint = make_preview_ready_sprint()
    paid = Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        status=PaymentStatus.PAID,
        provider_order_id="order_paid",
        provider_payment_id="pay_paid",
        paid_at=timezone.now(),
    )
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        status=PaymentStatus.FAILED,
        provider_order_id="order_failed_after_paid",
    )

    current = RazorpayPaymentService.current_payment(user=user, sprint=sprint)

    assert current == paid


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_rejects_missing_amount_currency_and_order_id():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    valid_entity = {
        "id": "pay_missing_fields",
        "order_id": payment.provider_order_id,
        "amount": payment.amount,
        "currency": payment.currency,
    }
    for missing_key in ["amount", "currency", "order_id"]:
        entity = dict(valid_entity)
        entity.pop(missing_key)
        body = _webhook_body_with_entity(entity, event_id=f"evt_missing_{missing_key}")

        with pytest.raises(PaymentProcessingError):
            RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED


@pytest.mark.django_db
@PAYMENT_SETTINGS
def test_webhook_rejects_currency_mismatch():
    user, sprint = make_preview_ready_sprint()
    payment = RazorpayPaymentService(client=FakeRazorpayClient()).create_or_reuse_order(
        user=user, sprint=sprint
    )
    body = webhook_body(order_id=payment.provider_order_id, currency="USD")

    with pytest.raises(PaymentProcessingError):
        RazorpayPaymentService().process_webhook(raw_body=body, signature=sign(body))

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.ORDER_CREATED
