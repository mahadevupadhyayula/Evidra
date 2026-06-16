from datetime import timedelta

import pytest
from django.utils import timezone

from ai.client import AIClientError, MockAIClient
from ai.services import EvidraAIService
from apps.generations.models import GenerationOperation, GenerationRun, GenerationRunStatus
from apps.generations.services import GenerationRunService
from apps.previews.models import ReadinessPreview
from apps.sprints.models import SprintState
from tests.previews.helpers import make_matching_ready_sprint, preview_response


@pytest.mark.django_db
def test_enqueue_preview_creates_one_active_run_and_reuses_duplicate():
    user, sprint, *_rest = make_matching_ready_sprint()

    first = GenerationRunService.enqueue_preview(user=user, sprint=sprint)
    second = GenerationRunService.enqueue_preview(user=user, sprint=sprint)

    assert first.pk == second.pk
    assert GenerationRun.objects.filter(status=GenerationRunStatus.PENDING).count() == 1
    assert first.operation == GenerationOperation.GENERATE_PREVIEW


@pytest.mark.django_db
def test_enqueue_preview_requires_owned_sprint(django_user_model):
    user, sprint, *_rest = make_matching_ready_sprint()
    other = django_user_model.objects.create_user(username="other@example.com")

    with pytest.raises(PermissionError):
        GenerationRunService.enqueue_preview(user=other, sprint=sprint)


@pytest.mark.django_db
def test_process_next_generates_preview_and_marks_run_succeeded():
    user, sprint, _profile, evidence, story, _alternative, match = make_matching_ready_sprint()
    run = GenerationRunService.enqueue_preview(user=user, sprint=sprint)
    ai_service = EvidraAIService(
        client=MockAIClient(responses=[preview_response(match, story, evidence)])
    )

    processed = GenerationRunService.process_next(ai_service=ai_service)

    assert processed.pk == run.pk
    processed.refresh_from_db()
    sprint.refresh_from_db()
    assert processed.status == GenerationRunStatus.SUCCEEDED
    assert processed.attempt_count == 1
    assert processed.completed_at is not None
    assert sprint.state == SprintState.PREVIEW_READY
    assert ReadinessPreview.objects.filter(sprint=sprint, status="READY").exists()


@pytest.mark.django_db
def test_structural_retry_is_owned_by_ai_service_and_failure_is_redacted():
    user, sprint, *_rest = make_matching_ready_sprint()
    run = GenerationRunService.enqueue_preview(user=user, sprint=sprint)
    ai_service = EvidraAIService(
        client=MockAIClient(
            responses=[
                AIClientError("api_key=secret raw provider failure"),
                AIClientError("still has api_key=secret"),
            ]
        )
    )

    GenerationRunService.process_next(ai_service=ai_service)

    run.refresh_from_db()
    assert run.status == GenerationRunStatus.FAILED
    assert run.error_code == "STRUCTURAL_VALIDATION_FAILED"
    assert "api_key=secret" not in run.error_message
    assert run.attempt_count == 1


@pytest.mark.django_db
def test_recover_abandoned_requeues_once_then_fails():
    user, sprint, *_rest = make_matching_ready_sprint()
    input_revision = GenerationRunService.current_preview_input_revision(user=user, sprint=sprint)
    old_started = timezone.now() - timedelta(minutes=60)
    run = GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision=input_revision,
        status=GenerationRunStatus.RUNNING,
        attempt_count=1,
        started_at=old_started,
    )

    assert GenerationRunService.recover_abandoned(abandoned_after_minutes=30) == 1
    run.refresh_from_db()
    assert run.status == GenerationRunStatus.PENDING
    assert run.started_at is None

    run.status = GenerationRunStatus.RUNNING
    run.attempt_count = 2
    run.started_at = old_started
    run.save(update_fields=["status", "attempt_count", "started_at", "updated_at"])

    assert GenerationRunService.recover_abandoned(abandoned_after_minutes=30) == 1
    run.refresh_from_db()
    assert run.status == GenerationRunStatus.FAILED
    assert run.error_code == "ABANDONED_RUN_FAILED"


@pytest.mark.django_db
def test_stale_pending_run_is_not_processed_when_inputs_change(monkeypatch):
    user, sprint, _profile, _evidence, story, *_rest = make_matching_ready_sprint()
    run = GenerationRunService.enqueue_preview(user=user, sprint=sprint)
    story.title = "Updated story title"
    story.save(update_fields=["title", "updated_at"])

    def fail_if_called(**_kwargs):
        raise AssertionError("stale generation run should not generate a preview")

    monkeypatch.setattr(
        "apps.generations.services.ReadinessPreviewService.generate_preview",
        fail_if_called,
    )

    GenerationRunService.process_next()

    run.refresh_from_db()
    assert run.status == GenerationRunStatus.STALE
    assert run.error_code == "INPUTS_CHANGED"
    assert run.completed_at is not None
    assert not ReadinessPreview.objects.filter(sprint=sprint).exists()


@pytest.mark.django_db
def test_abandoned_run_with_changed_inputs_is_marked_stale_not_requeued():
    user, sprint, _profile, _evidence, story, *_rest = make_matching_ready_sprint()
    input_revision = GenerationRunService.current_preview_input_revision(user=user, sprint=sprint)
    old_started = timezone.now() - timedelta(minutes=60)
    run = GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision=input_revision,
        status=GenerationRunStatus.RUNNING,
        attempt_count=1,
        started_at=old_started,
    )
    story.title = "Updated story title"
    story.save(update_fields=["title", "updated_at"])

    assert GenerationRunService.recover_abandoned(abandoned_after_minutes=30) == 1

    run.refresh_from_db()
    assert run.status == GenerationRunStatus.STALE
    assert run.error_code == "INPUTS_CHANGED"
    assert run.completed_at is not None
