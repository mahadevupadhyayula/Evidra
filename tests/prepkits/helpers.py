from django.utils import timezone

from apps.payments.models import Payment, PaymentStatus
from apps.sprints.models import SprintState
from tests.payments.helpers import make_preview_ready_sprint


def make_paid_sprint(username="prepkit@example.com"):
    user, sprint = make_preview_ready_sprint(username)
    Payment.objects.create(
        user=user,
        sprint=sprint,
        amount=499900,
        currency="INR",
        provider_order_id="order_prepkit",
        provider_payment_id="pay_prepkit",
        paid_at=timezone.now(),
        status=PaymentStatus.PAID,
    )
    sprint.state = SprintState.PAID
    sprint.save(update_fields=["state", "updated_at"])
    return user, sprint
