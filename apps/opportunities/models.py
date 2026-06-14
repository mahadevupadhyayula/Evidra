from django.db import models
from django.db.models import Q


class RoleFamily(models.TextChoices):
    PRODUCT_MANAGEMENT = "PRODUCT_MANAGEMENT", "Product Management"
    AI_PRODUCT_MANAGEMENT = "AI_PRODUCT_MANAGEMENT", "AI Product Management"
    SOFTWARE_ENGINEERING = "SOFTWARE_ENGINEERING", "Software Engineering"
    DATA_ANALYTICS = "DATA_ANALYTICS", "Data and Analytics"
    SALES_BUSINESS_DEVELOPMENT = (
        "SALES_BUSINESS_DEVELOPMENT",
        "Sales and Business Development",
    )
    CONSULTING_STRATEGY_OPS = "CONSULTING_STRATEGY_OPS", "Consulting/Strategy/Ops"
    OTHER = "OTHER", "Other"


class OpportunityStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    STALE = "STALE", "Stale"


class Opportunity(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="opportunities",
    )
    role_title = models.CharField(max_length=255)
    role_family = models.CharField(max_length=64, choices=RoleFamily.choices, db_index=True)
    target_seniority = models.CharField(max_length=128)
    company_name = models.CharField(max_length=255)
    job_description = models.TextField()
    interview_stage = models.CharField(max_length=128, blank=True)
    interview_date = models.DateField(null=True, blank=True)
    concerns = models.TextField(blank=True)
    improvement_goals = models.TextField(blank=True)
    jd_analysis = models.JSONField(null=True, blank=True)
    confirmation_status = models.CharField(
        max_length=32,
        choices=OpportunityStatus.choices,
        default=OpportunityStatus.DRAFT,
        db_index=True,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["sprint", "confirmation_status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint"],
                condition=~Q(confirmation_status=OpportunityStatus.STALE),
                name="one_current_opportunity_per_sprint",
            )
        ]

    def __str__(self) -> str:
        return f"Opportunity {self.pk} ({self.confirmation_status})"
