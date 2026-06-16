from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.payments.models import Payment, PaymentStatus
from apps.previews.models import ReadinessPreview, ReadinessPreviewStatus
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
    SprintWorkflowService,
)


class PaymentConfigurationError(RuntimeError):
    """Raised when Razorpay payment settings are incomplete."""


class PaymentProcessingError(ValueError):
    """Raised when a payment operation fails deterministic validation."""


@dataclass(frozen=True)
class PaymentWebhookResult:
    payment: Payment | None
    duplicate: bool = False
    processed: bool = False
    message: str = ""


class RazorpayPaymentService:
    SUCCESS_EVENTS = {"payment.captured"}
    FAILURE_EVENTS = {"payment.failed"}
    ACTIVE_STATUSES = {PaymentStatus.ORDER_CREATED, PaymentStatus.PAYMENT_PENDING}

    def __init__(self, *, client: Any | None = None) -> None:
        self.client = client

    @staticmethod
    def configured_amount() -> int:
        amount = int(getattr(settings, "INTERVIEW_SPRINT_PRICE_AMOUNT", 0) or 0)
        if amount <= 0:
            raise PaymentConfigurationError("Interview Sprint price amount is not configured.")
        return amount

    @staticmethod
    def configured_currency() -> str:
        currency = (getattr(settings, "INTERVIEW_SPRINT_PRICE_CURRENCY", "") or "").upper()
        if len(currency) != 3:
            raise PaymentConfigurationError("Interview Sprint price currency is not configured.")
        return currency

    @staticmethod
    def public_key_id() -> str:
        key_id = getattr(settings, "RAZORPAY_KEY_ID", "") or ""
        if not key_id:
            raise PaymentConfigurationError("Razorpay key ID is not configured.")
        return key_id

    @staticmethod
    def webhook_secret() -> str:
        secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or ""
        if not secret:
            raise PaymentConfigurationError("Razorpay webhook secret is not configured.")
        return secret

    def _client(self):
        if self.client is not None:
            return self.client
        key_id = self.public_key_id()
        key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "") or ""
        if not key_secret:
            raise PaymentConfigurationError("Razorpay key secret is not configured.")
        import razorpay

        return razorpay.Client(auth=(key_id, key_secret))

    def create_or_reuse_order(self, *, user, sprint: InterviewSprint) -> Payment:
        self._validate_checkout_owner_and_stage(user=user, sprint=sprint)
        amount = self.configured_amount()
        currency = self.configured_currency()

        existing = self.current_payment(user=user, sprint=sprint)
        if existing and existing.status == PaymentStatus.PAID:
            return existing
        if (
            existing
            and existing.status in self.ACTIVE_STATUSES
            and existing.amount == amount
            and existing.currency == currency
            and existing.provider_order_id
        ):
            SprintWorkflowService.mark_payment_pending(user=user, sprint=sprint, payment=existing)
            existing.refresh_from_db()
            return existing

        with transaction.atomic():
            payment = Payment.objects.create(
                user=user,
                sprint=sprint,
                provider=Payment.PROVIDER_RAZORPAY,
                amount=amount,
                currency=currency,
                status=PaymentStatus.NOT_STARTED,
            )

        receipt = f"sprint-{sprint.id}-payment-{payment.id}"
        try:
            order = self._client().order.create(
                {
                    "amount": amount,
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                    "notes": {"sprint_id": str(sprint.id), "payment_id": str(payment.id)},
                }
            )
        except Exception as exc:
            payment.status = PaymentStatus.FAILED
            payment.failure_code = "ORDER_CREATION_FAILED"
            payment.failure_message = str(exc)
            payment.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            raise PaymentProcessingError(
                "Could not create a Razorpay order. Please try again."
            ) from exc

        order_id = order.get("id")
        order_amount = int(order.get("amount") or 0)
        order_currency = str(order.get("currency") or "").upper()
        if not order_id or order_amount != amount or order_currency != currency:
            payment.status = PaymentStatus.FAILED
            payment.failure_code = "ORDER_VALIDATION_FAILED"
            payment.failure_message = (
                "Razorpay order did not match the expected amount or currency."
            )
            payment.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            raise PaymentProcessingError("Razorpay order validation failed.")

        payment.provider_order_id = order_id
        payment.status = PaymentStatus.ORDER_CREATED
        payment.save(update_fields=["provider_order_id", "status", "updated_at"])
        SprintWorkflowService.mark_payment_pending(user=user, sprint=sprint, payment=payment)
        payment.refresh_from_db()
        return payment

    def checkout_context(self, *, user, sprint: InterviewSprint) -> dict[str, Any]:
        payment = self.create_or_reuse_order(user=user, sprint=sprint)
        return {
            "payment": payment,
            "razorpay_key_id": self.public_key_id(),
            "provider_order_id": payment.provider_order_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "product_name": "Evidra Interview Sprint Prep Kit",
        }

    @staticmethod
    def current_payment(*, user, sprint: InterviewSprint) -> Payment | None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        paid_payment = (
            Payment.objects.filter(user=user, sprint=sprint, status=PaymentStatus.PAID)
            .order_by("-paid_at", "-id")
            .first()
        )
        if paid_payment is not None:
            return paid_payment
        return (
            Payment.objects.filter(user=user, sprint=sprint)
            .order_by("-created_at", "-id")
            .first()
        )

    def retry_payment(self, *, user, sprint: InterviewSprint) -> Payment:
        current = self.current_payment(user=user, sprint=sprint)
        if current and current.status == PaymentStatus.PAID:
            return current
        return self.create_or_reuse_order(user=user, sprint=sprint)

    def process_webhook(self, *, raw_body: bytes, signature: str) -> PaymentWebhookResult:
        self._validate_webhook_signature(raw_body=raw_body, signature=signature)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PaymentProcessingError("Webhook payload is not valid JSON.") from exc

        event_id = str(payload.get("id") or payload.get("event_id") or "")
        event_type = str(payload.get("event") or "")
        payment_entity = self._payment_entity(payload)
        order_entity = self._order_entity(payload)
        provider_order_id = str(
            payment_entity.get("order_id")
            or order_entity.get("id")
            or payload.get("order_id")
            or ""
        )
        if not provider_order_id:
            raise PaymentProcessingError("Webhook did not include a Razorpay order ID.")

        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("user", "sprint")
                .filter(provider=Payment.PROVIDER_RAZORPAY, provider_order_id=provider_order_id)
                .first()
            )
            if payment is None:
                raise PaymentProcessingError("Webhook order does not match a local payment.")
            if event_id and payment.webhook_event_id == event_id:
                return PaymentWebhookResult(payment=payment, duplicate=True, processed=False)
            self._validate_webhook_amount_and_order(payment=payment, payment_entity=payment_entity)

            if event_type in self.SUCCESS_EVENTS:
                return self._process_success(
                    payment=payment, event_id=event_id, payment_entity=payment_entity
                )
            if event_type in self.FAILURE_EVENTS:
                return self._process_failure(
                    payment=payment, event_id=event_id, payment_entity=payment_entity
                )
            return PaymentWebhookResult(
                payment=payment, duplicate=False, processed=False, message="ignored"
            )

    def _process_success(
        self, *, payment: Payment, event_id: str, payment_entity: dict[str, Any]
    ) -> PaymentWebhookResult:
        provider_payment_id = str(payment_entity.get("id") or payment.provider_payment_id or "")
        if not provider_payment_id:
            raise PaymentProcessingError("Successful webhook did not include a payment ID.")
        now = timezone.now()
        if payment.status != PaymentStatus.PAID:
            payment.status = PaymentStatus.PAID
            payment.paid_at = payment.paid_at or now
        payment.provider_payment_id = provider_payment_id
        payment.webhook_event_id = event_id or payment.webhook_event_id
        payment.webhook_received_at = now
        payment.failure_code = ""
        payment.failure_message = ""
        payment.save(
            update_fields=[
                "status",
                "provider_payment_id",
                "webhook_event_id",
                "webhook_received_at",
                "paid_at",
                "failure_code",
                "failure_message",
                "updated_at",
            ]
        )
        SprintWorkflowService.mark_paid(user=payment.user, sprint=payment.sprint, payment=payment)
        return PaymentWebhookResult(payment=payment, processed=True)

    @staticmethod
    def _process_failure(
        *, payment: Payment, event_id: str, payment_entity: dict[str, Any]
    ) -> PaymentWebhookResult:
        if payment.status == PaymentStatus.PAID:
            return PaymentWebhookResult(payment=payment, processed=False, message="ignored_paid")
        error = payment_entity.get("error") or {}
        payment.status = PaymentStatus.FAILED
        payment.provider_payment_id = str(
            payment_entity.get("id") or payment.provider_payment_id or ""
        )
        payment.webhook_event_id = event_id or payment.webhook_event_id
        payment.webhook_received_at = timezone.now()
        payment.failure_code = str(
            payment_entity.get("error_code") or error.get("code") or "PAYMENT_FAILED"
        )
        payment.failure_message = str(
            payment_entity.get("error_description") or error.get("description") or "Payment failed."
        )
        payment.save(
            update_fields=[
                "status",
                "provider_payment_id",
                "webhook_event_id",
                "webhook_received_at",
                "failure_code",
                "failure_message",
                "updated_at",
            ]
        )
        return PaymentWebhookResult(payment=payment, processed=True)

    def _validate_webhook_signature(self, *, raw_body: bytes, signature: str) -> None:
        if not signature:
            raise PaymentProcessingError("Missing Razorpay webhook signature.")
        digest = hmac.new(
            self.webhook_secret().encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(digest, signature):
            raise PaymentProcessingError("Invalid Razorpay webhook signature.")

    @staticmethod
    def _payment_entity(payload: dict[str, Any]) -> dict[str, Any]:
        return (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
            or payload.get("payment", {})
            or {}
        )

    @staticmethod
    def _order_entity(payload: dict[str, Any]) -> dict[str, Any]:
        return (
            payload.get("payload", {}).get("order", {}).get("entity", {})
            or payload.get("order", {})
            or {}
        )

    @staticmethod
    def _validate_webhook_amount_and_order(
        *, payment: Payment, payment_entity: dict[str, Any]
    ) -> None:
        provider_order_id = str(payment_entity.get("order_id") or "")
        if not provider_order_id:
            raise PaymentProcessingError("Webhook payment entity is missing an order ID.")
        if provider_order_id != payment.provider_order_id:
            raise PaymentProcessingError("Webhook order does not match the stored payment order.")
        if payment_entity.get("amount") is None:
            raise PaymentProcessingError("Webhook payment entity is missing an amount.")
        if not payment_entity.get("currency"):
            raise PaymentProcessingError("Webhook payment entity is missing a currency.")
        try:
            amount = int(payment_entity["amount"])
        except (TypeError, ValueError) as exc:
            raise PaymentProcessingError("Webhook amount is invalid.") from exc
        currency = str(payment_entity["currency"]).upper()
        if amount != payment.amount or currency != payment.currency:
            raise PaymentProcessingError("Webhook amount or currency does not match the order.")

    @staticmethod
    def _validate_checkout_owner_and_stage(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        allowed_states = {SprintState.PREVIEW_READY, SprintState.PAYMENT_PENDING}
        if SprintState(sprint.state) not in allowed_states:
            raise InvalidSprintTransition(
                f"Cannot start payment while Sprint is in {sprint.state}."
            )
        if not ReadinessPreview.objects.filter(
            sprint=sprint,
            sprint__user=user,
            status=ReadinessPreviewStatus.READY,
        ).exists():
            raise SprintTransitionConditionMissing("A ready preview is required before payment.")
