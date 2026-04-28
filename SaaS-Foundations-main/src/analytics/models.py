from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class UserActivity(models.Model):
    """Tracks user actions for ML analysis."""
    class ActionChoices(models.TextChoices):
        PAGE_VIEW = 'page_view', 'Page View'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        PROFILE_UPDATE = 'profile_update', 'Profile Update'
        BILLING_VIEW = 'billing_view', 'Billing View'
        PRICING_VIEW = 'pricing_view', 'Pricing View'
        SUPPORT_CONTACT = 'support_contact', 'Support Contact'
        FEATURE_USE = 'feature_use', 'Feature Use'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action = models.CharField(max_length=50, choices=ActionChoices.choices)
    path = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'User Activities'
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.user} — {self.action} @ {self.timestamp}"


class MLPrediction(models.Model):
    """Stores ML predictions for each user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ml_prediction')
    churn_probability = models.FloatField(default=0.0, help_text="0-100 probability of churn")
    health_score = models.IntegerField(default=50, help_text="0-100 account health")
    engagement_level = models.CharField(max_length=20, default="medium")
    predicted_usage_next_month = models.IntegerField(default=0)
    recommendations = models.JSONField(default=list, blank=True)
    last_calculated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} — Health: {self.health_score}, Churn: {self.churn_probability}%"

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
