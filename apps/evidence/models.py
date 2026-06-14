from django.conf import settings
from django.db import models


class CareerHighlightStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    STALE = "STALE", "Stale"


class EvidenceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    NEEDS_DETAIL = "NEEDS_DETAIL", "Needs detail"
    STALE = "STALE", "Stale"


class CareerHighlight(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="career_highlights",
    )
    profile = models.ForeignKey(
        "profiles.CareerProfile",
        on_delete=models.CASCADE,
        related_name="career_highlights",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    metric = models.CharField(max_length=255, null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    source_note = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=CareerHighlightStatus.choices,
        default=CareerHighlightStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "profile", "status"])]

    def __str__(self) -> str:
        return f"Career highlight {self.pk} ({self.status})"


class EvidenceCard(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evidence_cards",
    )
    profile = models.ForeignKey(
        "profiles.CareerProfile",
        on_delete=models.CASCADE,
        related_name="evidence_cards",
    )
    source_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_cards",
    )
    source_highlight = models.ForeignKey(
        "evidence.CareerHighlight",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_cards",
    )
    title = models.CharField(max_length=255)
    problem = models.TextField(null=True, blank=True)
    role = models.TextField(null=True, blank=True)
    action = models.TextField(null=True, blank=True)
    result = models.TextField(null=True, blank=True)
    metric = models.CharField(max_length=255, null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    competencies = models.JSONField(default=list, blank=True)
    ownership_signal = models.TextField(null=True, blank=True)
    constraints = models.TextField(null=True, blank=True)
    tradeoffs = models.TextField(null=True, blank=True)
    missing_details = models.JSONField(default=list, blank=True)
    source_excerpt = models.TextField()
    source_location = models.CharField(max_length=255, blank=True)
    confidentiality = models.BooleanField(default=False)
    status = models.CharField(
        max_length=32,
        choices=EvidenceStatus.choices,
        default=EvidenceStatus.DRAFT,
        db_index=True,
    )
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicate_suggestions",
    )
    duplicate_reason = models.TextField(blank=True)
    ai_generated_data = models.JSONField(default=dict, blank=True)
    user_edited_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "profile", "status"]),
            models.Index(fields=["profile", "status"]),
            models.Index(fields=["source_document"]),
            models.Index(fields=["source_highlight"]),
        ]

    def __str__(self) -> str:
        return f"Evidence card {self.pk} ({self.status})"
