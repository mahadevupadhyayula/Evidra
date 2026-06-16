import pytest
from django.urls import reverse

from apps.generations.models import GenerationRun, GenerationRunStatus
from apps.generations.services import GenerationRunService
from tests.previews.helpers import make_matching_ready_sprint


@pytest.mark.django_db
def test_preview_generate_view_queues_generation_run(client):
    user, sprint, *_rest = make_matching_ready_sprint()
    client.force_login(user)

    response = client.post(reverse("previews:generate"))

    assert response.status_code == 302
    assert (
        GenerationRun.objects.filter(sprint=sprint, status=GenerationRunStatus.PENDING).count()
        == 1
    )


@pytest.mark.django_db
def test_preview_status_fragment_polls_for_active_run(client):
    user, sprint, *_rest = make_matching_ready_sprint()
    GenerationRunService.enqueue_preview(user=user, sprint=sprint)
    client.force_login(user)

    response = client.get(reverse("previews:generation_status_poll"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'hx-get="/workspace/preview/generation/status/poll/"' in content
    assert "Pending" in content


@pytest.mark.django_db
def test_preview_status_fragment_redacts_failed_error(client):
    user, sprint, *_rest = make_matching_ready_sprint()
    GenerationRun.objects.create(
        sprint=sprint,
        operation="GENERATE_PREVIEW",
        input_revision="rev",
        status=GenerationRunStatus.FAILED,
        error_code="OPERATION_FAILED",
        error_message="Generation failed. Please try again.",
    )
    client.force_login(user)

    response = client.get(reverse("previews:generation_status_poll"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Generation failed. Please try again." in content
    assert "Traceback" not in content
