from django.db import models
from django.db.models import Q


class PrepKitStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    READY = "READY", "Ready"
    FAILED = "FAILED", "Failed"
    STALE = "STALE", "Stale"


class PrepKit(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="prep_kits",
    )
    status = models.CharField(
        max_length=32,
        choices=PrepKitStatus.choices,
        default=PrepKitStatus.PENDING,
        db_index=True,
    )
    role_briefing = models.JSONField(default=dict, blank=True)
    fit_summary = models.JSONField(default=dict, blank=True)
    competency_coverage = models.JSONField(default=list, blank=True)
    story_map = models.JSONField(default=list, blank=True)
    question_bank = models.JSONField(default=list, blank=True)
    concern_map = models.JSONField(default=list, blank=True)
    missing_evidence = models.JSONField(default=list, blank=True)
    practice_priorities = models.JSONField(default=list, blank=True)
    seven_day_plan = models.JSONField(default=list, blank=True)
    interview_checklist = models.JSONField(default=list, blank=True)
    input_revision = models.CharField(max_length=128, db_index=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["sprint", "status"]),
            models.Index(fields=["sprint", "input_revision"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "input_revision"],
                condition=Q(status__in=[PrepKitStatus.PENDING, PrepKitStatus.READY]),
                name="one_current_prepkit_per_sprint_revision",
            )
        ]

    def __str__(self) -> str:
        return f"Prep Kit {self.pk} ({self.status})"
