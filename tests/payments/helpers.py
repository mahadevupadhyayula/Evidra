import hashlib
import hmac
import json

from django.test import override_settings

from apps.previews.models import ReadinessPreview
from apps.sprints.models import SprintState
from tests.previews.helpers import make_matching_ready_sprint

PAYMENT_SETTINGS = override_settings(
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="rzp_test_secret",
    RAZORPAY_WEBHOOK_SECRET="whsec_test",
    INTERVIEW_SPRINT_PRICE_AMOUNT=499900,
    INTERVIEW_SPRINT_PRICE_CURRENCY="INR",
)


class FakeRazorpayClient:
    def __init__(self, *, order_id="order_test", amount=499900, currency="INR", fail=False):
        self.order = self
        self.order_id = order_id
        self.amount = amount
        self.currency = currency
        self.fail = fail
        self.created_payloads = []

    def create(self, payload):
        if self.fail:
            raise RuntimeError("provider unavailable")
        self.created_payloads.append(payload)
        return {"id": self.order_id, "amount": self.amount, "currency": self.currency}


def make_preview_ready_sprint(username="payment@example.com"):
    (
        user,
        sprint,
        _profile,
        evidence,
        story,
        _alternative,
        match,
    ) = make_matching_ready_sprint(username)
    ReadinessPreview.objects.create(
        sprint=sprint,
        role_summary="Role summary",
        competencies=[{"label": "Product strategy", "readiness": "covered"}],
        strengths=[{"title": "Strength", "explanation": "Grounded."}],
        gaps=[{"title": "Gap", "explanation": "Practice."}],
        evidence_completeness={"summary": "Evidence", "approved_evidence_count": 1},
        story_coverage={"summary": "Stories", "ready_story_count": 1},
        matched_story_excerpt={
            "story_id": story.id,
            "match_id": match.id,
            "title": story.title,
            "excerpt": story.short_answer,
            "evidence_ids": [evidence.id],
        },
        prepkit_explanation="The paid Prep Kit expands this preview.",
        input_revision="payment-revision",
        status="READY",
    )
    sprint.state = SprintState.PREVIEW_READY
    sprint.save(update_fields=["state", "updated_at"])
    return user, sprint


def webhook_body(
    *,
    event="payment.captured",
    event_id="evt_test",
    order_id="order_test",
    payment_id="pay_test",
    amount=499900,
    currency="INR",
):
    return json.dumps(
        {
            "id": event_id,
            "event": event,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount,
                        "currency": currency,
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def sign(body, secret="whsec_test"):
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
