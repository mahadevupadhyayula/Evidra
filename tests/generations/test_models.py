import pytest
from django.db import IntegrityError

from apps.generations.models import GenerationOperation, GenerationRun, GenerationRunStatus
from tests.previews.helpers import make_matching_ready_sprint


@pytest.mark.django_db
def test_generation_run_statuses_and_str():
    _user, sprint, *_rest = make_matching_ready_sprint()
    run = GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision="rev-1",
    )

    assert {choice.value for choice in GenerationRunStatus} == {
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "STALE",
    }
    assert "GENERATE_PREVIEW" in str(run)


@pytest.mark.django_db
def test_duplicate_active_generation_run_is_prevented():
    _user, sprint, *_rest = make_matching_ready_sprint()
    GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision="same",
        status=GenerationRunStatus.PENDING,
    )

    with pytest.raises(IntegrityError):
        GenerationRun.objects.create(
            sprint=sprint,
            operation=GenerationOperation.GENERATE_PREVIEW,
            input_revision="same",
            status=GenerationRunStatus.RUNNING,
        )


@pytest.mark.django_db
def test_terminal_generation_runs_preserve_failure_history():
    _user, sprint, *_rest = make_matching_ready_sprint()
    GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision="same",
        status=GenerationRunStatus.FAILED,
    )
    second = GenerationRun.objects.create(
        sprint=sprint,
        operation=GenerationOperation.GENERATE_PREVIEW,
        input_revision="same",
        status=GenerationRunStatus.PENDING,
    )

    assert second.pk
