from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.utils import timezone
import os

User = settings.AUTH_USER_MODEL


class TaskerProfile(models.Model):
    """Profile for users who complete assignments (taskers)"""
    class KYCStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class CompetencyStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        FLAGGED = "flagged", "Flagged"

    class InterviewStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        SCHEDULED = "scheduled", "Scheduled"
        PASSED = "passed", "Passed"
        UNDER_REVIEW = "under_review", "Under Review"
        FAILED = "failed", "Failed"

    class ApprovalStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    SKILL_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tasker_profile')
    skills = models.TextField(help_text="Comma-separated list of skills (e.g., 'Python, Data Analysis, ML')")
    skill_level = models.CharField(max_length=20, choices=SKILL_LEVEL_CHOICES, default='beginner')
    bio = models.TextField(blank=True, null=True, help_text="Brief bio about tasker's experience")
    completed_assignments = models.IntegerField(default=0)
    success_rate = models.FloatField(default=0.0, help_text="Percentage of successfully completed assignments")
    availability_hours_per_week = models.IntegerField(default=20)
    is_active_tasker = models.BooleanField(default=True)
    home_region = models.ForeignKey(
        "operations.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taskers",
    )
    competency_areas = models.ManyToManyField(
        "trust.CompetencyArea",
        blank=True,
        related_name="taskers",
    )
    kyc_status = models.CharField(max_length=20, choices=KYCStatus.choices, default=KYCStatus.PENDING)
    competency_status = models.CharField(max_length=20, choices=CompetencyStatus.choices, default=CompetencyStatus.PENDING)
    interview_status = models.CharField(max_length=20, choices=InterviewStatus.choices, default=InterviewStatus.NOT_STARTED)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    trust_score = models.FloatField(default=0.0)
    quality_score = models.FloatField(default=0.0)
    on_time_delivery_rate = models.FloatField(default=0.0)
    revision_frequency = models.FloatField(default=0.0)
    fraud_risk_score = models.FloatField(default=0.0)
    reliability_score = models.FloatField(default=0.0)
    current_workload_hours = models.FloatField(default=0.0)
    last_ai_score = models.FloatField(default=0.0)
    admin_approved = models.BooleanField(default=False)
    is_accepting_work = models.BooleanField(default=False)
    last_assessed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-trust_score', '-quality_score', '-completed_assignments']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.skill_level}"


class Assignment(models.Model):
    """Main assignment model for writing tasks that need to be completed"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assignments')
    title = models.CharField(max_length=255)
    description = models.TextField()
    required_skills = models.TextField(help_text="Comma-separated skills needed (e.g., 'Python, Database Design')")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Deadline and timing
    deadline = models.DateTimeField(null=True, blank=True)
    estimated_hours = models.IntegerField(help_text="Estimated hours to complete")

    # Assignment tracking
    assigned_to = models.ForeignKey(TaskerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments')
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    budget_cents = models.IntegerField(null=True, blank=True, help_text="Budget in cents (e.g., 10000 = $100)")
    ml_match_score = models.FloatField(default=0.0, help_text="ML engine match score with assigned tasker")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def assign_to_tasker(self, tasker_profile):
        """Assign this assignment to a tasker and mark as in progress"""
        self.assigned_to = tasker_profile
        self.assigned_at = timezone.now()
        self.status = 'in_progress'
        self.save()


class AssignmentFile(models.Model):
    """Files attached to assignments (instructions, documents, data files, etc.)"""
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(
        upload_to='assignments/%Y/%m/%d/',
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'xlsx', 'csv', 'zip', 'jpg', 'png', 'py', 'js', 'json']
        )]
    )
    file_type = models.CharField(max_length=50, help_text="e.g., 'instruction', 'data', 'reference', 'submission'")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size_mb = models.FloatField(help_text="File size in MB")
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.assignment.title} - {os.path.basename(self.file.name)}"

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size_mb = self.file.size / (1024 * 1024)
        super().save(*args, **kwargs)


class AssignmentAssignment(models.Model):
    """Through model tracking individual assignments of assignments to taskers"""
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='task_assignments')
    tasker = models.ForeignKey(TaskerProfile, on_delete=models.CASCADE, related_name='assigned_tasks')
    assigned_at = models.DateTimeField(auto_now_add=True)
    ml_match_score = models.FloatField()
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('assignment', 'tasker')
        ordering = ['-ml_match_score']

    def __str__(self):
        return f"{self.assignment.title} → {self.tasker.user.username}"


class AssignmentSubmission(models.Model):
    """Submissions from taskers when they complete assignments"""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    tasker = models.ForeignKey(TaskerProfile, on_delete=models.CASCADE, related_name='assignment_submissions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    submission_text = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    reviewer_notes = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_submissions')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    rating = models.IntegerField(null=True, blank=True, help_text="Rating out of 5")

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Submission: {self.assignment.title} by {self.tasker.user.username}"
