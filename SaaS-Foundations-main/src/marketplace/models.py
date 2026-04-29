from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, FileExtensionValidator
from django.db import models
from django.utils import timezone


User = settings.AUTH_USER_MODEL


class TaskCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=64, blank=True, default="sparkles")
    active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class TaskOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        QUALITY_REVIEW = "quality_review", "Quality Review"
        REVISION = "revision", "Revision"
        COMPLETED = "completed", "Completed"
        ESCALATED = "escalated", "Escalated"
        CANCELLED = "cancelled", "Cancelled"
        ARCHIVED = "archived", "Archived"

    class Complexity(models.TextChoices):
        ESSENTIAL = "essential", "Essential"
        STANDARD = "standard", "Standard"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        ESCROWED = "escrowed", "Escrowed"
        RELEASED = "released", "Released"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="marketplace_tasks",
    )
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=160)
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    competency_area = models.ForeignKey(
        "trust.CompetencyArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    description = models.TextField(blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    deadline = models.DateTimeField(null=True, blank=True)
    estimated_hours = models.PositiveIntegerField(default=0)
    budget_cents = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    pricing_suggestion_cents = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="USD")
    complexity_level = models.CharField(
        max_length=20,
        choices=Complexity.choices,
        default=Complexity.STANDARD,
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    assigned_tasker = models.ForeignKey(
        "assignments.TaskerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_tasks",
    )
    region_preference = models.ForeignKey(
        "operations.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    required_trust_score = models.FloatField(default=60.0)
    deadline_feasibility_score = models.FloatField(default=0.0)
    assignment_confidence = models.FloatField(default=0.0)
    quality_score = models.FloatField(default=0.0)
    revision_count = models.PositiveIntegerField(default=0)
    platform_fee_cents = models.PositiveIntegerField(default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    ai_estimate = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["assigned_tasker", "status"]),
            models.Index(fields=["deadline", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def publish(self):
        if self.status == self.Status.DRAFT:
            self.set_status(self.Status.OPEN, actor=self.student, actor_role="student", note="Published by student")
            if self.published_at is None:
                self.published_at = timezone.now()
                self.save(update_fields=["published_at", "updated_at"])

    def set_status(self, new_status, actor=None, note="", payload=None, actor_role="system"):
        previous_status = self.status
        self.status = new_status
        if new_status == self.Status.OPEN and self.published_at is None:
            self.published_at = timezone.now()
        if new_status == self.Status.ASSIGNED and self.assigned_at is None:
            self.assigned_at = timezone.now()
        if new_status == self.Status.COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        if new_status == self.Status.CANCELLED and self.cancelled_at is None:
            self.cancelled_at = timezone.now()
        self.save()
        TaskStatusEvent.objects.create(
            task=self,
            previous_status=previous_status,
            new_status=new_status,
            actor=actor,
            actor_role=actor_role,
            note=note,
            payload=payload or {},
        )

    def assign_tasker(self, tasker, actor=None, score=None, confidence=None, rationale=None, selected_by="ai"):
        self.assigned_tasker = tasker
        if score is not None:
            self.assignment_confidence = score
        if confidence is not None:
            self.assignment_confidence = confidence
        if rationale:
            self.ai_estimate = {
                **(self.ai_estimate or {}),
                "assignment_rationale": rationale,
                "selected_by": selected_by,
            }
        if self.status in {self.Status.DRAFT, self.Status.OPEN}:
            self.set_status(
                self.Status.ASSIGNED,
                actor=actor,
                actor_role=selected_by,
                note="Task assigned through marketplace matching",
                payload={"tasker_id": tasker.id, "selected_by": selected_by},
            )
        else:
            self.save()

    @property
    def is_active_pipeline(self):
        return self.status in {
            self.Status.OPEN,
            self.Status.ASSIGNED,
            self.Status.IN_PROGRESS,
            self.Status.QUALITY_REVIEW,
            self.Status.REVISION,
            self.Status.ESCALATED,
        }


class TaskAttachment(models.Model):
    class FileKind(models.TextChoices):
        INSTRUCTION = "instruction", "Instruction"
        REFERENCE = "reference", "Reference"
        SUPPORTING = "supporting", "Supporting"
        SUBMISSION = "submission", "Submission"
        REVISION = "revision", "Revision"
        OTHER = "other", "Other"

    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(
        upload_to="marketplace/tasks/%Y/%m/%d/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf",
                    "doc",
                    "docx",
                    "txt",
                    "xlsx",
                    "csv",
                    "zip",
                    "jpg",
                    "png",
                    "jpeg",
                    "json",
                ]
            )
        ],
    )
    file_kind = models.CharField(max_length=32, choices=FileKind.choices, default=FileKind.OTHER)
    description = models.TextField(blank=True, default="")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size_mb = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.task.title} - {self.file.name}"

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size_mb = round(self.file.size / (1024 * 1024), 2)
        super().save(*args, **kwargs)


class TaskMatchSuggestion(models.Model):
    class SuggestionState(models.TextChoices):
        RECOMMENDED = "recommended", "Recommended"
        BACKUP = "backup", "Backup"
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"

    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="match_suggestions")
    tasker = models.ForeignKey("assignments.TaskerProfile", on_delete=models.CASCADE, related_name="match_suggestions")
    score = models.FloatField(default=0.0)
    confidence = models.FloatField(default=0.0)
    ranking_position = models.PositiveIntegerField(default=1)
    state = models.CharField(
        max_length=20,
        choices=SuggestionState.choices,
        default=SuggestionState.RECOMMENDED,
    )
    rationale = models.JSONField(default=dict, blank=True)
    ai_snapshot = models.JSONField(default=dict, blank=True)
    selected_by = models.CharField(max_length=40, default="ai")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ranking_position", "-score"]
        unique_together = ("task", "tasker")

    def __str__(self):
        return f"{self.task.title} → {self.tasker}"


class TaskStatusEvent(models.Model):
    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="status_events")
    previous_status = models.CharField(max_length=30, blank=True, default="")
    new_status = models.CharField(max_length=30)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_status_events")
    actor_role = models.CharField(max_length=40, blank=True, default="system")
    note = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task.title}: {self.previous_status} → {self.new_status}"


class TaskSubmission(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        NEEDS_REVISION = "needs_revision", "Needs Revision"
        REJECTED = "rejected", "Rejected"

    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="submissions")
    tasker = models.ForeignKey("assignments.TaskerProfile", on_delete=models.CASCADE, related_name="submissions")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    submission_text = models.TextField(blank=True, default="")
    file = models.FileField(
        upload_to="marketplace/submissions/%Y/%m/%d/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf",
                    "doc",
                    "docx",
                    "txt",
                    "xlsx",
                    "csv",
                    "zip",
                    "jpg",
                    "png",
                    "jpeg",
                ]
            )
        ],
    )
    summary = models.TextField(blank=True, default="")
    quality_score = models.FloatField(default=0.0)
    ai_quality_score = models.FloatField(default=0.0)
    student_feedback = models.TextField(blank=True, default="")
    reviewer_notes = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        unique_together = ("task", "tasker", "version")

    def __str__(self):
        return f"{self.task.title} v{self.version}"


class TaskRevisionRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    submission = models.ForeignKey(TaskSubmission, on_delete=models.CASCADE, related_name="revision_requests")
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    due_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Revision request for {self.submission}"


class TaskRating(models.Model):
    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="ratings")
    tasker = models.ForeignKey("assignments.TaskerProfile", on_delete=models.CASCADE, related_name="ratings")
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_ratings")
    overall_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    accuracy_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    communication_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    speed_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    comments = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("task", "client")

    def __str__(self):
        return f"{self.task.title} rating by {self.client}"


class TaskPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        ESCROWED = "escrowed", "Escrowed"
        RELEASED = "released", "Released"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="payments")
    amount_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=8, default="USD")
    provider = models.CharField(max_length=40, default="paystack")
    provider_reference = models.CharField(max_length=140, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    escrow_status = models.CharField(max_length=20, default="not_started")
    paid_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task.title} payment ({self.status})"


class TaskConversationMessage(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In App"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="messages", null=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_messages")
    is_ai = models.BooleanField(default=False)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} message @ {self.created_at:%Y-%m-%d %H:%M}"


class TaskNotification(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        IN_APP = "in_app", "In App"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_notifications")
    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    title = models.CharField(max_length=140)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} → {self.recipient}"


class TaskAuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_audit_events")
    actor_role = models.CharField(max_length=40, blank=True, default="system")
    task = models.ForeignKey(TaskOrder, on_delete=models.CASCADE, related_name="audit_events", null=True, blank=True)
    entity_type = models.CharField(max_length=80, blank=True, default="task")
    entity_id = models.CharField(max_length=80, blank=True, default="")
    event_type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M}"
