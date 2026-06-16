from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from ai.services import AIPreviewGenerationError, EvidraAIService
from apps.generations.models import GenerationOperation, GenerationRun, GenerationRunStatus
from apps.previews.services import ReadinessPreviewError, ReadinessPreviewService
from apps.sprints.models import InterviewSprint, SprintState
from apps.sprints.services import (
    InvalidSprintTransition,
    SprintOwnershipError,
    SprintTransitionConditionMissing,
)


class GenerationRunError(ValueError):
    """Raised when a generation run cannot be created or processed safely."""


class GenerationRunProcessingError(RuntimeError):
    """Raised when an operational worker action cannot safely continue."""


@dataclass(frozen=True)
class GenerationRunService:
    ABANDONED_AFTER_MINUTES = 30
    MAX_WORKER_ATTEMPTS = 2
    STRUCTURAL_ERROR_TYPES = (AIPreviewGenerationError, ReadinessPreviewError)

    @staticmethod
    def enqueue_preview(*, user, sprint: InterviewSprint, force: bool = False) -> GenerationRun:
        GenerationRunService._require_owned_preview_sprint(user=user, sprint=sprint)
        input_revision = GenerationRunService.current_preview_input_revision(
            user=user, sprint=sprint
        )
        if not force:
            existing_ready = ReadinessPreviewService.current_preview(user=user, sprint=sprint)
            if existing_ready and existing_ready.input_revision == input_revision:
                return GenerationRunService._get_or_create_succeeded_run(
                    sprint=sprint,
                    operation=GenerationOperation.GENERATE_PREVIEW,
                    input_revision=input_revision,
                )

        operation = GenerationOperation.GENERATE_PREVIEW
        try:
            with transaction.atomic():
                GenerationRun.objects.select_for_update().filter(
                    sprint=sprint,
                    sprint__user=user,
                    operation=operation,
                    status__in=GenerationRun.ACTIVE_STATUSES,
                ).exclude(input_revision=input_revision).update(
                    status=GenerationRunStatus.STALE,
                    error_code="INPUTS_CHANGED",
                    error_message="Inputs changed before this generation could finish.",
                    completed_at=timezone.now(),
                )
                existing = (
                    GenerationRun.objects.select_for_update()
                    .filter(
                        sprint=sprint,
                        sprint__user=user,
                        operation=operation,
                        input_revision=input_revision,
                        status__in=GenerationRun.ACTIVE_STATUSES,
                    )
                    .order_by("created_at", "id")
                    .first()
                )
                if existing is not None:
                    return existing
                return GenerationRun.objects.create(
                    sprint=sprint,
                    operation=operation,
                    input_revision=input_revision,
                    status=GenerationRunStatus.PENDING,
                )
        except IntegrityError:
            existing = GenerationRun.objects.filter(
                sprint=sprint,
                sprint__user=user,
                operation=operation,
                input_revision=input_revision,
                status__in=GenerationRun.ACTIVE_STATUSES,
            ).first()
            if existing is not None:
                return existing
            raise

    @staticmethod
    def current_preview_run(*, user, sprint: InterviewSprint) -> GenerationRun | None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        return (
            GenerationRun.objects.filter(
                sprint=sprint,
                sprint__user=user,
                operation=GenerationOperation.GENERATE_PREVIEW,
            )
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def claim_next_pending(*, operation: str | None = None) -> GenerationRun | None:
        with transaction.atomic():
            runs: QuerySet[GenerationRun] = GenerationRun.objects.select_for_update(
                skip_locked=True
            ).filter(status=GenerationRunStatus.PENDING)
            if operation:
                runs = runs.filter(operation=operation)
            run = runs.select_related("sprint", "sprint__user").order_by("created_at", "id").first()
            if run is None:
                return None
            run.status = GenerationRunStatus.RUNNING
            run.started_at = timezone.now()
            run.completed_at = None
            run.error_code = ""
            run.error_message = ""
            run.attempt_count += 1
            run.save(
                update_fields=[
                    "status",
                    "started_at",
                    "completed_at",
                    "error_code",
                    "error_message",
                    "attempt_count",
                    "updated_at",
                ]
            )
            return run

    @staticmethod
    def process_next(
        *, operation: str | None = None, ai_service: EvidraAIService | None = None
    ) -> GenerationRun | None:
        run = GenerationRunService.claim_next_pending(operation=operation)
        if run is None:
            return None
        GenerationRunService.process_run(run=run, ai_service=ai_service)
        return GenerationRun.objects.get(pk=run.pk)

    @staticmethod
    def process_batch(
        *, limit: int = 10, operation: str | None = None, ai_service: EvidraAIService | None = None
    ) -> int:
        processed = 0
        for _index in range(limit):
            run = GenerationRunService.process_next(operation=operation, ai_service=ai_service)
            if run is None:
                break
            processed += 1
        return processed

    @staticmethod
    def process_run(*, run: GenerationRun, ai_service: EvidraAIService | None = None) -> None:
        run = GenerationRun.objects.select_related("sprint", "sprint__user").get(pk=run.pk)
        if run.status != GenerationRunStatus.RUNNING:
            raise GenerationRunProcessingError("Only running generation runs can be processed.")
        if not GenerationRunService._run_matches_current_input_revision(run=run):
            GenerationRunService.mark_stale(
                run=run,
                error_code="INPUTS_CHANGED",
                error_message="Inputs changed before this generation could finish.",
            )
            return
        try:
            if run.operation == GenerationOperation.GENERATE_PREVIEW:
                ReadinessPreviewService.generate_preview(
                    user=run.sprint.user,
                    sprint=run.sprint,
                    ai_service=ai_service,
                    force=True,
                )
            else:
                raise GenerationRunError("Unknown generation operation.")
        except Exception as exc:  # noqa: BLE001 - worker records failures for every run safely.
            code, message = GenerationRunService.redact_error(exc)
            GenerationRunService.mark_failed(run=run, error_code=code, error_message=message)
            return
        GenerationRunService.mark_succeeded(run=run)

    @staticmethod
    def recover_abandoned(*, abandoned_after_minutes: int | None = None) -> int:
        threshold = timezone.now() - timedelta(
            minutes=abandoned_after_minutes or GenerationRunService.ABANDONED_AFTER_MINUTES
        )
        recovered = 0
        with transaction.atomic():
            abandoned = list(
                GenerationRun.objects.select_for_update()
                .filter(status=GenerationRunStatus.RUNNING, started_at__lt=threshold)
                .order_by("started_at", "id")
            )
            now = timezone.now()
            for run in abandoned:
                if not GenerationRunService._run_matches_current_input_revision(run=run):
                    run.status = GenerationRunStatus.STALE
                    run.error_code = "INPUTS_CHANGED"
                    run.error_message = "Inputs changed before this generation could finish."
                    run.completed_at = now
                    run.save(
                        update_fields=[
                            "status",
                            "error_code",
                            "error_message",
                            "completed_at",
                            "updated_at",
                        ]
                    )
                elif run.attempt_count >= GenerationRunService.MAX_WORKER_ATTEMPTS:
                    run.status = GenerationRunStatus.FAILED
                    run.error_code = "ABANDONED_RUN_FAILED"
                    run.error_message = "Generation failed after the worker stopped unexpectedly."
                    run.completed_at = now
                    run.save(
                        update_fields=[
                            "status",
                            "error_code",
                            "error_message",
                            "completed_at",
                            "updated_at",
                        ]
                    )
                else:
                    run.status = GenerationRunStatus.PENDING
                    run.started_at = None
                    run.error_code = "ABANDONED_RUN_RECOVERED"
                    run.error_message = (
                        "Generation was re-queued after the worker stopped unexpectedly."
                    )
                    run.save(
                        update_fields=[
                            "status",
                            "started_at",
                            "error_code",
                            "error_message",
                            "updated_at",
                        ]
                    )
                recovered += 1
        return recovered

    @staticmethod
    def mark_succeeded(*, run: GenerationRun) -> None:
        with transaction.atomic():
            locked = GenerationRun.objects.select_for_update().get(pk=run.pk)
            if locked.status != GenerationRunStatus.RUNNING:
                return
            locked.status = GenerationRunStatus.SUCCEEDED
            locked.error_code = ""
            locked.error_message = ""
            locked.completed_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )

    @staticmethod
    def mark_failed(*, run: GenerationRun, error_code: str, error_message: str) -> None:
        with transaction.atomic():
            locked = GenerationRun.objects.select_for_update().get(pk=run.pk)
            if locked.status != GenerationRunStatus.RUNNING:
                return
            locked.status = GenerationRunStatus.FAILED
            locked.error_code = error_code[:64]
            locked.error_message = error_message[:2000]
            locked.completed_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )

    @staticmethod
    def mark_stale(*, run: GenerationRun, error_code: str, error_message: str) -> None:
        with transaction.atomic():
            locked = GenerationRun.objects.select_for_update().get(pk=run.pk)
            if locked.status not in GenerationRun.ACTIVE_STATUSES:
                return
            locked.status = GenerationRunStatus.STALE
            locked.error_code = error_code[:64]
            locked.error_message = error_message[:2000]
            locked.completed_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "updated_at",
                ]
            )

    @staticmethod
    def redact_error(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, GenerationRunError):
            return "INVALID_OPERATION", "Generation could not be routed safely."
        if isinstance(exc, GenerationRunService.STRUCTURAL_ERROR_TYPES):
            return (
                "STRUCTURAL_VALIDATION_FAILED",
                "Generation returned invalid structured output. Please try again.",
            )
        if isinstance(
            exc,
            (InvalidSprintTransition, SprintTransitionConditionMissing, SprintOwnershipError),
        ):
            return "VALIDATION_FAILED", "Generation cannot run for the current Sprint state."
        return "OPERATION_FAILED", "Generation failed. Please try again."

    @staticmethod
    def current_preview_input_revision(*, user, sprint: InterviewSprint) -> str:
        GenerationRunService._require_owned_preview_sprint(user=user, sprint=sprint)
        opportunity = ReadinessPreviewService._get_confirmed_opportunity(user=user, sprint=sprint)
        matches = ReadinessPreviewService._matches(user=user, sprint=sprint)
        if not matches:
            raise SprintTransitionConditionMissing("Contextual matches are required for preview.")
        stories = ReadinessPreviewService._ready_stories(user=user, sprint=sprint)
        if not stories:
            raise SprintTransitionConditionMissing("Ready stories are required for preview.")
        evidence = ReadinessPreviewService._approved_evidence(user=user, sprint=sprint)
        if not evidence:
            raise SprintTransitionConditionMissing("Approved evidence is required for preview.")
        if ReadinessPreviewService._excerpt_match(matches=matches) is None:
            raise SprintTransitionConditionMissing(
                "A credible matched story is required for preview."
            )
        return ReadinessPreviewService.build_input_revision(
            sprint=sprint,
            opportunity=opportunity,
            matches=matches,
            stories=stories,
            evidence=evidence,
        )

    @staticmethod
    def _run_matches_current_input_revision(*, run: GenerationRun) -> bool:
        if run.operation != GenerationOperation.GENERATE_PREVIEW:
            return False
        try:
            current_revision = GenerationRunService.current_preview_input_revision(
                user=run.sprint.user, sprint=run.sprint
            )
        except (
            InvalidSprintTransition,
            SprintOwnershipError,
            SprintTransitionConditionMissing,
        ):
            return False
        return run.input_revision == current_revision

    @staticmethod
    def _get_or_create_succeeded_run(
        *, sprint: InterviewSprint, operation: GenerationOperation, input_revision: str
    ) -> GenerationRun:
        run = (
            GenerationRun.objects.filter(
                sprint=sprint,
                operation=operation,
                input_revision=input_revision,
                status=GenerationRunStatus.SUCCEEDED,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if run is not None:
            return run
        return GenerationRun.objects.create(
            sprint=sprint,
            operation=operation,
            input_revision=input_revision,
            status=GenerationRunStatus.SUCCEEDED,
            completed_at=timezone.now(),
        )

    @staticmethod
    def _require_owned_preview_sprint(*, user, sprint: InterviewSprint) -> None:
        if not user.is_authenticated or sprint.user_id != user.id:
            raise SprintOwnershipError("Sprint is not owned by this user.")
        if SprintState(sprint.state) not in {SprintState.MATCHING_READY, SprintState.PREVIEW_READY}:
            raise InvalidSprintTransition(
                f"Cannot use preview generation while Sprint is in {sprint.state}."
            )
