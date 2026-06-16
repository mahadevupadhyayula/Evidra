from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.payments.models import Payment
from apps.prepkits.services import PrepKitService
from tests.prepkits.helpers import make_paid_sprint


def make_practice_ready_sprint(username="practice@example.com"):
    user, sprint = make_paid_sprint(username)
    Payment.objects.filter(user=user, sprint=sprint).update(
        provider_order_id=f"order_{sprint.id}", provider_payment_id=f"pay_{sprint.id}"
    )
    prepkit = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    sprint.refresh_from_db()
    return user, sprint, prepkit
