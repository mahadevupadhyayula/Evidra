from django.db import models


class StoryMatch(models.Model):
    sprint = models.ForeignKey(
        "sprints.InterviewSprint",
        on_delete=models.CASCADE,
        related_name="story_matches",
    )
    competency_key = models.CharField(max_length=128, db_index=True)
    competency_label = models.CharField(max_length=255, blank=True)
    primary_story = models.ForeignKey(
        "stories.Story",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="primary_matches",
    )
    alternative_story = models.ForeignKey(
        "stories.Story",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alternative_matches",
    )
    selected_story = models.ForeignKey(
        "stories.Story",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="selected_matches",
    )
    competency_score = models.PositiveSmallIntegerField(default=0)
    role_relevance_score = models.PositiveSmallIntegerField(default=0)
    seniority_score = models.PositiveSmallIntegerField(default=0)
    evidence_strength_score = models.PositiveSmallIntegerField(default=0)
    company_context_score = models.PositiveSmallIntegerField(default=0)
    total_score = models.PositiveSmallIntegerField(default=0, db_index=True)
    explanation = models.TextField(blank=True)
    jd_excerpt = models.TextField(blank=True)
    evidence_ids = models.JSONField(default=list, blank=True)
    missing_signal = models.TextField(blank=True)
    recommended_emphasis = models.TextField(blank=True)
    user_selected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["competency_key", "-total_score", "-created_at"]
        indexes = [
            models.Index(fields=["sprint", "competency_key"]),
            models.Index(fields=["sprint", "user_selected"]),
            models.Index(fields=["sprint", "total_score"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sprint", "competency_key"],
                name="one_story_match_per_sprint_competency",
            )
        ]

    def __str__(self) -> str:
        return f"Story match {self.pk} ({self.competency_key})"
