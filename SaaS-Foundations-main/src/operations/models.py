from django.conf import settings
from django.db import models


User = settings.AUTH_USER_MODEL


class Region(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120, unique=True)
    timezone = models.CharField(max_length=80, blank=True, default="UTC")
    countries = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    staff_target = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ManagerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="manager_profile")
    title = models.CharField(max_length=120, default="Regional Manager")
    regions = models.ManyToManyField(Region, blank=True, related_name="managers")
    active = models.BooleanField(default=True)
    can_reassign_tasks = models.BooleanField(default=True)
    can_review_applications = models.BooleanField(default=True)
    escalation_limit = models.PositiveIntegerField(default=25)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class RegionalAssignment(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="tasker_assignments")
    tasker = models.ForeignKey("assignments.TaskerProfile", on_delete=models.CASCADE, related_name="regional_assignments")
    manager = models.ForeignKey(ManagerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="regional_assignments")
    active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-assigned_at"]
        unique_together = ("region", "tasker")

    def __str__(self):
        return f"{self.tasker} -> {self.region}"


class EscalationCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        TRIAGED = "triaged", "Triaged"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    task = models.ForeignKey("marketplace.TaskOrder", on_delete=models.CASCADE, related_name="escalations")
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="escalations")
    opened_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="opened_escalations")
    assigned_manager = models.ForeignKey(ManagerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="escalations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    reason = models.TextField()
    resolution = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Escalation for {self.task.title}"


class QualityAudit(models.Model):
    task = models.ForeignKey("marketplace.TaskOrder", on_delete=models.CASCADE, related_name="quality_audits")
    manager = models.ForeignKey(ManagerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="quality_audits")
    audit_score = models.FloatField(default=0.0)
    outcome = models.CharField(max_length=80, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Audit {self.task.title}"


class TaskerPerformanceSnapshot(models.Model):
    tasker = models.ForeignKey("assignments.TaskerProfile", on_delete=models.CASCADE, related_name="performance_snapshots")
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="performance_snapshots")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    accuracy_score = models.FloatField(default=0.0)
    on_time_rate = models.FloatField(default=0.0)
    revision_rate = models.FloatField(default=0.0)
    earnings_cents = models.PositiveIntegerField(default=0)
    quality_rating = models.FloatField(default=0.0)
    fraud_risk_score = models.FloatField(default=0.0)
    reliability_score = models.FloatField(default=0.0)
    ranking_score = models.FloatField(default=0.0)
    task_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end"]
        unique_together = ("tasker", "period_start", "period_end")

    def __str__(self):
        return f"{self.tasker} snapshot {self.period_start:%Y-%m-%d}"

