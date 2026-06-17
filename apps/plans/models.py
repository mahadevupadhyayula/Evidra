from django.db import models
from django.db.models import Q


class ImprovementPlanStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    STALE = "STALE", "Stale"


class PlanTaskStatus(models.TextChoices):
    TODO = "TODO", "Todo"
    DONE = "DONE", "Done"
    SKIPPED = "SKIPPED", "Skipped"


class PlanTaskType(models.TextChoices):
    EVIDENCE_GAP = "EVIDENCE_GAP", "Evidence gap"
    STORY_IMPROVEMENT = "STORY_IMPROVEMENT", "Story improvement"
    MATCH_GAP = "MATCH_GAP", "Match gap"
    PRACTICE = "PRACTICE", "Practice"
    COMPANY_RESEARCH = "COMPANY_RESEARCH", "Company research"
    USER_GOAL = "USER_GOAL", "User goal"
    FINAL_REVIEW = "FINAL_REVIEW", "Final review"


class ImprovementPlan(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="improvement_plans",
    )
    status = models.CharField(
        max_length=32,
        choices=ImprovementPlanStatus.choices,
        default=ImprovementPlanStatus.ACTIVE,
        db_index=True,
    )
    interview_date = models.DateField(null=True, blank=True)
    plan_length_days = models.PositiveSmallIntegerField(default=7)
    generated_from_revision = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["sprint", "status"]),
            models.Index(fields=["sprint", "generated_from_revision"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint"],
                condition=Q(status__in=[ImprovementPlanStatus.DRAFT, ImprovementPlanStatus.ACTIVE]),
                name="one_current_improvement_plan_per_sprint",
            )
        ]

    def __str__(self) -> str:
        return f"Improvement plan {self.pk} ({self.status})"


class PlanTask(models.Model):
    plan = models.ForeignKey(
        "plans.ImprovementPlan",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    day_number = models.PositiveSmallIntegerField(db_index=True)
    task_type = models.CharField(max_length=64, choices=PlanTaskType.choices, db_index=True)
    title = models.CharField(max_length=255)
    reason = models.TextField()
    instructions = models.TextField()
    estimated_minutes = models.PositiveSmallIntegerField()
    linked_evidence = models.ForeignKey(
        "evidence.EvidenceCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_tasks",
    )
    linked_story = models.ForeignKey(
        "stories.Story",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_tasks",
    )
    linked_question_id = models.CharField(max_length=128, blank=True)
    priority = models.PositiveSmallIntegerField(db_index=True)
    status = models.CharField(
        max_length=32,
        choices=PlanTaskStatus.choices,
        default=PlanTaskStatus.TODO,
        db_index=True,
    )
    task_fingerprint = models.CharField(max_length=128, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["day_number", "-priority", "id"]
        indexes = [
            models.Index(fields=["plan", "day_number"]),
            models.Index(fields=["plan", "status"]),
            models.Index(fields=["linked_evidence"]),
            models.Index(fields=["linked_story"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(day_number__gte=1, day_number__lte=7),
                name="plan_task_day_between_1_and_7",
            ),
            models.CheckConstraint(
                condition=Q(estimated_minutes__gte=5, estimated_minutes__lte=45),
                name="plan_task_estimated_minutes_between_5_and_45",
            ),
            models.UniqueConstraint(
                fields=["plan", "task_fingerprint"],
                name="one_plan_task_per_fingerprint",
            ),
        ]

    def __str__(self) -> str:
        return f"Plan task {self.pk} (day {self.day_number}, {self.status})"
