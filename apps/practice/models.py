from django.db import models


class PracticeAttempt(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="practice_attempts",
    )
    question_id = models.CharField(max_length=128, db_index=True)
    linked_story = models.ForeignKey(
        "stories.Story",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="practice_attempts",
    )
    answer_text = models.TextField()
    relevance_score = models.PositiveSmallIntegerField()
    structure_score = models.PositiveSmallIntegerField()
    specificity_score = models.PositiveSmallIntegerField()
    ownership_score = models.PositiveSmallIntegerField()
    impact_score = models.PositiveSmallIntegerField()
    clarity_score = models.PositiveSmallIntegerField()
    feedback = models.JSONField(default=dict, blank=True)
    improved_answer = models.TextField()
    follow_up_question = models.TextField()
    attempt_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["sprint", "question_id", "-created_at"]),
            models.Index(fields=["sprint", "-created_at"]),
            models.Index(fields=["linked_story"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "question_id", "attempt_number"],
                name="one_practice_attempt_number_per_question",
            )
        ]

    def __str__(self) -> str:
        return f"Practice attempt {self.pk} ({self.question_id} #{self.attempt_number})"
