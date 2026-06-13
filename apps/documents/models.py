from django.conf import settings
from django.db import models
from django.db.models import Q


class DocumentType(models.TextChoices):
    RESUME = "RESUME", "Resume"


class DocumentParsingStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    VALIDATING = "VALIDATING", "Validating"
    PARSING = "PARSING", "Parsing"
    READY_FOR_REVIEW = "READY_FOR_REVIEW", "Ready for review"
    CONFIRMED = "CONFIRMED", "Confirmed"
    INVALID_FILE = "INVALID_FILE", "Invalid file"
    PARSING_FAILED = "PARSING_FAILED", "Parsing failed"
    REPLACED = "REPLACED", "Replaced"


class Document(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=32,
        choices=DocumentType.choices,
        default=DocumentType.RESUME,
        db_index=True,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    storage_key = models.CharField(max_length=512, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    raw_text = models.TextField(blank=True)
    cleaned_text = models.TextField(blank=True)
    parsing_status = models.CharField(
        max_length=32,
        choices=DocumentParsingStatus.choices,
        default=DocumentParsingStatus.UPLOADED,
        db_index=True,
    )
    parsing_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "document_type", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(document_type=DocumentType.RESUME, is_active=True),
                name="one_active_resume_document_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document_type} document {self.pk} ({self.parsing_status})"
