from django.conf import settings
from django.db import models


class StoryStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready"
    EDITED = "EDITED", "Edited"
    STALE = "STALE", "Stale"
    ARCHIVED = "ARCHIVED", "Archived"


class Story(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stories",
    )
    profile = models.ForeignKey(
        "profiles.CareerProfile",
        on_delete=models.CASCADE,
        related_name="stories",
    )
    title = models.CharField(max_length=255)
    story_type = models.CharField(max_length=64, blank=True)
    situation = models.TextField(null=True, blank=True)
    task = models.TextField(null=True, blank=True)
    action = models.TextField(null=True, blank=True)
    result = models.TextField(null=True, blank=True)
    learning = models.TextField(null=True, blank=True)
    short_answer = models.TextField()
    ninety_second_answer = models.TextField()
    detailed_answer = models.TextField()
    competency_tags = models.JSONField(default=list, blank=True)
    seniority_signals = models.JSONField(default=list, blank=True)
    evidence_ids = models.JSONField(default=list, blank=True)
    specificity_score = models.PositiveSmallIntegerField(null=True, blank=True)
    impact_score = models.PositiveSmallIntegerField(null=True, blank=True)
    ownership_score = models.PositiveSmallIntegerField(null=True, blank=True)
    clarity_score = models.PositiveSmallIntegerField(null=True, blank=True)
    quality_score = models.PositiveSmallIntegerField(null=True, blank=True)
    missing_details = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=32,
        choices=StoryStatus.choices,
        default=StoryStatus.DRAFT,
        db_index=True,
    )
    source_story = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisions",
    )
    revision_number = models.PositiveSmallIntegerField(default=1)
    ai_generated_data = models.JSONField(default=dict, blank=True)
    user_edited_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["user", "profile", "status"]),
            models.Index(fields=["profile", "status"]),
            models.Index(fields=["source_story"]),
        ]

    def __str__(self) -> str:
        return f"Story {self.pk} ({self.status})"


class StoryGenerationFailure(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="story_generation_failures",
    )
    profile = models.ForeignKey(
        "profiles.CareerProfile",
        on_delete=models.CASCADE,
        related_name="story_generation_failures",
    )
    operation = models.CharField(max_length=32)
    error_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "profile", "operation"])]

    def __str__(self) -> str:
        return f"Story generation failure {self.pk} ({self.operation})"
