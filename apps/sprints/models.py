from django.conf import settings
from django.db import models
from django.db.models import Q


class SprintState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    RESUME_READY = "RESUME_READY", "Resume ready"
    PROFILE_CONFIRMED = "PROFILE_CONFIRMED", "Profile confirmed"
    OPPORTUNITY_CONFIRMED = "OPPORTUNITY_CONFIRMED", "Opportunity confirmed"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW", "Evidence review"
    EVIDENCE_APPROVED = "EVIDENCE_APPROVED", "Evidence approved"
    STORIES_READY = "STORIES_READY", "Stories ready"
    MATCHING_READY = "MATCHING_READY", "Matching ready"
    PREVIEW_READY = "PREVIEW_READY", "Preview ready"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    PAID = "PAID", "Paid"
    PREPKIT_READY = "PREPKIT_READY", "Prep Kit ready"
    PRACTICE_ACTIVE = "PRACTICE_ACTIVE", "Practice active"
    PLAN_READY = "PLAN_READY", "Plan ready"
    COMPLETED = "COMPLETED", "Completed"


class InterviewSprint(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interview_sprints",
    )
    active_resume = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_sprints",
    )
    active_profile = models.ForeignKey(
        "profiles.CareerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_for_sprints",
    )
    state = models.CharField(
        max_length=32,
        choices=SprintState.choices,
        default=SprintState.DRAFT,
        db_index=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "state"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=~Q(state=SprintState.COMPLETED),
                name="one_current_interview_sprint_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"Interview Sprint {self.pk} ({self.state})"
