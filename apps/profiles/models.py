from django.conf import settings
from django.db import models
from django.db.models import Q


class CareerProfileStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    STALE = "STALE", "Stale"


class ProfileExtractionStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not started"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class CareerProfile(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="career_profiles",
    )
    active_resume = models.ForeignKey(
        "documents.Document",
        on_delete=models.PROTECT,
        related_name="career_profiles",
    )
    full_name = models.CharField(max_length=255, null=True, blank=True)
    current_role = models.CharField(max_length=255, null=True, blank=True)
    current_company = models.CharField(max_length=255, null=True, blank=True)
    years_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    industries = models.JSONField(default=list, blank=True)
    functional_areas = models.JSONField(default=list, blank=True)
    skills = models.JSONField(default=list, blank=True)
    tools = models.JSONField(default=list, blank=True)
    education_summary = models.TextField(null=True, blank=True)
    career_summary = models.TextField(null=True, blank=True)
    positioning_summary = models.TextField(null=True, blank=True)
    extraction_status = models.CharField(
        max_length=32,
        choices=ProfileExtractionStatus.choices,
        default=ProfileExtractionStatus.NOT_STARTED,
    )
    extraction_error = models.TextField(blank=True)
    ai_attempt_count = models.PositiveSmallIntegerField(default=0)
    confirmation_status = models.CharField(
        max_length=32,
        choices=CareerProfileStatus.choices,
        default=CareerProfileStatus.DRAFT,
        db_index=True,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "confirmation_status"]),
            models.Index(fields=["user", "active_resume"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "active_resume"],
                condition=~Q(confirmation_status=CareerProfileStatus.STALE),
                name="one_current_profile_per_resume",
            )
        ]

    def __str__(self) -> str:
        return f"Career profile {self.pk} ({self.confirmation_status})"
