from django.db import models
from django.db.models import Q


class GenerationOperation(models.TextChoices):
    GENERATE_PREVIEW = "GENERATE_PREVIEW", "Generate readiness preview"


class GenerationRunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    STALE = "STALE", "Stale"


class GenerationRun(models.Model):
    ACTIVE_STATUSES = [GenerationRunStatus.PENDING, GenerationRunStatus.RUNNING]
    TERMINAL_STATUSES = [
        GenerationRunStatus.SUCCEEDED,
        GenerationRunStatus.FAILED,
        GenerationRunStatus.STALE,
    ]

    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="generation_runs",
    )
    operation = models.CharField(
        max_length=64,
        choices=GenerationOperation.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=32,
        choices=GenerationRunStatus.choices,
        default=GenerationRunStatus.PENDING,
        db_index=True,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    input_revision = models.CharField(max_length=128, db_index=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["sprint", "operation", "status"]),
            models.Index(fields=["sprint", "operation", "input_revision"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "operation", "input_revision"],
                condition=Q(status__in=[GenerationRunStatus.PENDING, GenerationRunStatus.RUNNING]),
                name="one_active_generation_run_per_revision",
            )
        ]

    def __str__(self) -> str:
        return f"Generation run {self.pk} ({self.operation}, {self.status})"
