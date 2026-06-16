import pytest

from ai.client import MockAIClient
from ai.services import EvidraAIService
from apps.generations.models import GenerationOperation, GenerationRunStatus
from apps.generations.services import GenerationRunService
from apps.prepkits.models import PrepKit, PrepKitStatus
from apps.sprints.models import SprintState
from tests.prepkits.helpers import make_paid_sprint


@pytest.mark.django_db
def test_enqueue_prepkit_generation_is_idempotent():
    user, sprint = make_paid_sprint("enqueue-prepkit@example.com")

    first = GenerationRunService.enqueue_prepkit(user=user, sprint=sprint)
    second = GenerationRunService.enqueue_prepkit(user=user, sprint=sprint)

    assert first.pk == second.pk
    assert first.operation == GenerationOperation.GENERATE_PREPKIT


@pytest.mark.django_db
def test_process_prepkit_generation_run_creates_artifact_and_transitions():
    user, sprint = make_paid_sprint("process-prepkit@example.com")
    run = GenerationRunService.enqueue_prepkit(user=user, sprint=sprint)

    GenerationRunService.claim_next_pending(operation=GenerationOperation.GENERATE_PREPKIT)
    GenerationRunService.process_run(run=run, ai_service=EvidraAIService(client=MockAIClient()))

    run.refresh_from_db()
    sprint.refresh_from_db()
    assert run.status == GenerationRunStatus.SUCCEEDED
    assert sprint.state == SprintState.PREPKIT_READY
    assert PrepKit.objects.filter(sprint=sprint, status=PrepKitStatus.READY).exists()


@pytest.mark.django_db
def test_process_prepkit_generation_run_records_failure():
    user, sprint = make_paid_sprint("process-fail-prepkit@example.com")
    run = GenerationRunService.enqueue_prepkit(user=user, sprint=sprint)
    claimed = GenerationRunService.claim_next_pending(
        operation=GenerationOperation.GENERATE_PREPKIT
    )
    client = MockAIClient(responses=[{"role_briefing_points": []}, {}])

    GenerationRunService.process_run(run=claimed, ai_service=EvidraAIService(client=client))

    run.refresh_from_db()
    sprint.refresh_from_db()
    assert run.status == GenerationRunStatus.FAILED
    assert sprint.state == SprintState.PAID
    assert PrepKit.objects.filter(sprint=sprint, status=PrepKitStatus.FAILED).exists()
