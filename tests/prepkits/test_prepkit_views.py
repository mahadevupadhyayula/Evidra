import pytest

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.generations.models import GenerationOperation, GenerationRun
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.prepkits.services import PrepKitService
from tests.prepkits.helpers import make_paid_sprint


@pytest.mark.django_db
def test_prepkit_detail_requires_login(client):
    response = client.get("/workspace/prepkit/")

    assert response.status_code == 302


@pytest.mark.django_db
def test_paid_user_can_queue_prepkit_generation(client):
    user, sprint = make_paid_sprint("view-prepkit@example.com")
    client.force_login(user)

    response = client.post("/workspace/prepkit/generate/", follow=True)

    assert response.status_code == 200
    assert GenerationRun.objects.filter(
        sprint=sprint, operation=GenerationOperation.GENERATE_PREPKIT
    ).exists()


@pytest.mark.django_db
def test_prepkit_detail_displays_ready_sections(client):
    user, sprint = make_paid_sprint("ready-view-prepkit@example.com")
    PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    client.force_login(user)

    response = client.get("/workspace/prepkit/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Fit summary" in content
    assert "Question bank" in content
    assert "Seven-day plan draft" in content
    assert "Sources:" in content


@pytest.mark.django_db
def test_prepkit_print_renders_without_pdf_generator(client):
    user, sprint = make_paid_sprint("print-prepkit@example.com")
    PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    client.force_login(user)

    response = client.get("/workspace/prepkit/print/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Print-friendly Prep Kit" in content
    assert "PDF generation is not part" in content
    assert "Sources:" in content


@pytest.mark.django_db
def test_failed_prepkit_detail_shows_retry(client):
    user, sprint = make_paid_sprint("retry-view-prepkit@example.com")
    client.force_login(user)
    run = GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREPKIT,
        input_revision=PrepKitService.current_input_revision(user=user, sprint=sprint),
        status="FAILED",
        error_message="AI failed",
    )
    assert run.status == "FAILED"

    response = client.get("/workspace/prepkit/")
    content = response.content.decode()

    assert "Retry Prep Kit generation" in content


@pytest.mark.django_db
def test_failed_regeneration_keeps_previous_prepkit_visible(client):
    user, sprint = make_paid_sprint("previous-visible-prepkit@example.com")
    ready = PrepKitService.generate_prepkit(
        user=user, sprint=sprint, ai_service=EvidraAIService(client=MockAIClient())
    )
    ready.status = PrepKitStatus.STALE
    ready.save(update_fields=["status", "updated_at"])
    PrepKit.objects.create(
        sprint=sprint,
        input_revision="failed-current",
        status=PrepKitStatus.FAILED,
        error_message="AI failed",
    )
    client.force_login(user)

    response = client.get("/workspace/prepkit/")
    content = response.content.decode()

    assert "Generation failed" in content
    assert "previous Prep Kit remains available" in content
    assert "Paid Prep Kit" in content
