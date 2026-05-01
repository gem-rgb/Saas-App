from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class UserActivity(models.Model):
    """Tracks user actions for ML analysis."""

    class ActionChoices(models.TextChoices):
        PAGE_VIEW = "page_view", "Page View"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        PROFILE_UPDATE = "profile_update", "Profile Update"
        BILLING_VIEW = "billing_view", "Billing View"
        PRICING_VIEW = "pricing_view", "Pricing View"
        SUPPORT_CONTACT = "support_contact", "Support Contact"
        FEATURE_USE = "feature_use", "Feature Use"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    action = models.CharField(max_length=50, choices=ActionChoices.choices)
    path = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "User Activities"
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} @ {self.timestamp}"


class MLPrediction(models.Model):
    """Stores ML predictions for each user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ml_prediction")
    churn_probability = models.FloatField(default=0.0, help_text="0-100 probability of churn")
    health_score = models.IntegerField(default=50, help_text="0-100 account health")
    engagement_level = models.CharField(max_length=20, default="medium")
    predicted_usage_next_month = models.IntegerField(default=0)
    recommendations = models.JSONField(default=list, blank=True)
    last_calculated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} - Health: {self.health_score}, Engagement: {self.engagement_level}"

    @property
    def churn_risk_level(self):
        if self.churn_probability >= 70:
            return "high"
        elif self.churn_probability >= 40:
            return "medium"
        return "low"

    @property
    def health_color(self):
        if self.health_score >= 70:
            return "green"
        elif self.health_score >= 40:
            return "yellow"
        return "red"


class PlagiarismSnapshot(models.Model):
    """Persisted snapshot of a corpus or author writing profile for plagiarism checks."""

    class CacheType(models.TextChoices):
        CORPUS = "corpus", "Corpus"
        AUTHOR = "author", "Author"

    class SourceKind(models.TextChoices):
        MARKETPLACE = "marketplace", "Marketplace"
        ASSIGNMENTS = "assignments", "Assignments"

    cache_key = models.CharField(max_length=255, unique=True)
    cache_type = models.CharField(max_length=20, choices=CacheType.choices)
    source_kind = models.CharField(max_length=20, choices=SourceKind.choices)
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="plagiarism_snapshots",
    )
    payload = models.JSONField(default=dict, blank=True)
    source_hash = models.CharField(max_length=64, blank=True, default="")
    sample_text_count = models.PositiveIntegerField(default=0)
    source_window_days = models.PositiveIntegerField(default=30)
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-refreshed_at"]
        indexes = [
            models.Index(fields=["cache_type", "source_kind"]),
            models.Index(fields=["source_kind", "source_object_id"]),
            models.Index(fields=["author", "cache_type"]),
        ]

    def __str__(self):
        target = self.cache_key
        return f"{self.get_cache_type_display()} snapshot: {target}"

    @property
    def sample_texts(self):
        payload = self.payload if isinstance(self.payload, dict) else {}
        sample_texts = payload.get("sample_texts", [])
        return sample_texts if isinstance(sample_texts, list) else []

    @property
    def profile(self):
        payload = self.payload if isinstance(self.payload, dict) else {}
        profile = payload.get("profile", {})
        return profile if isinstance(profile, dict) else {}

    @property
    def reference_surprisal(self):
        payload = self.payload if isinstance(self.payload, dict) else {}
        try:
            return float(payload.get("reference_surprisal", 0.0))
        except (TypeError, ValueError):
            return 0.0
