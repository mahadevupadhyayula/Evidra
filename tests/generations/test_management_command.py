import pytest
from django.core.management import call_command

from apps.generations.models import GenerationRunStatus
from apps.generations.services import GenerationRunService
from tests.previews.helpers import make_matching_ready_sprint


@pytest.mark.django_db
def test_process_generation_runs_command_processes_pending_run(monkeypatch):
    user, sprint, *_rest = make_matching_ready_sprint()
    run = GenerationRunService.enqueue_preview(user=user, sprint=sprint)

    def fake_generate_preview(**kwargs):
        assert kwargs["user"] == user
        assert kwargs["sprint"] == sprint

    monkeypatch.setattr(
        "apps.generations.services.ReadinessPreviewService.generate_preview",
        fake_generate_preview,
    )

    call_command("process_generation_runs", limit=1, skip_abandoned_recovery=True)

    run.refresh_from_db()
    assert run.status == GenerationRunStatus.SUCCEEDED
