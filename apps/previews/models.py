from django.db import models
from django.db.models import Q


class ReadinessPreviewStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready"
    STALE = "STALE", "Stale"


class ReadinessPreview(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="readiness_previews",
    )
    role_summary = models.TextField()
    competencies = models.JSONField(default=list, blank=True)
    strengths = models.JSONField(default=list, blank=True)
    gaps = models.JSONField(default=list, blank=True)
    evidence_completeness = models.JSONField(default=dict, blank=True)
    story_coverage = models.JSONField(default=dict, blank=True)
    matched_story_excerpt = models.JSONField(default=dict, blank=True)
    prepkit_explanation = models.TextField()
    input_revision = models.CharField(max_length=128, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=ReadinessPreviewStatus.choices,
        default=ReadinessPreviewStatus.DRAFT,
        db_index=True,
    )
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
                condition=Q(
                    status__in=[ReadinessPreviewStatus.DRAFT, ReadinessPreviewStatus.READY]
                ),
                name="one_current_preview_per_sprint_revision",
            )
        ]

    def __str__(self) -> str:
        return f"Readiness preview {self.pk} ({self.status})"
