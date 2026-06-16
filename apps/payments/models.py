from django.conf import settings
from django.db import models
from django.db.models import Q


class PaymentStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not started"
    ORDER_CREATED = "ORDER_CREATED", "Order created"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"


class Payment(models.Model):
    PROVIDER_RAZORPAY = "razorpay"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    provider = models.CharField(max_length=32, default=PROVIDER_RAZORPAY, db_index=True)
    provider_order_id = models.CharField(max_length=128, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True, db_index=True)
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=32,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_STARTED,
        db_index=True,
    )
    webhook_event_id = models.CharField(max_length=128, blank=True, db_index=True)
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=128, blank=True)
    failure_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["sprint", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "provider", "provider_order_id"],
                condition=~Q(provider_order_id=""),
                name="unique_payment_order_per_sprint",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                condition=~Q(provider_payment_id=""),
                name="unique_provider_payment_id",
            ),
            models.UniqueConstraint(
                fields=["sprint"],
                condition=Q(status=PaymentStatus.PAID),
                name="one_paid_payment_per_sprint",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment {self.pk} ({self.status})"
