from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models


User = settings.AUTH_USER_MODEL


class CompetencyArea(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class TaskerApplication(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        DOCUMENT_REVIEW = "document_review", "Document Review"
        INTERVIEW_PENDING = "interview_pending", "Interview Pending"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    applicant = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tasker_application")
    tasker_profile = models.OneToOneField(
        "assignments.TaskerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_application",
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    headline = models.CharField(max_length=200, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    years_experience = models.PositiveIntegerField(default=0)
    education_level = models.CharField(max_length=120, blank=True, default="")
    portfolio_url = models.URLField(blank=True, default="")
    region_preference = models.ForeignKey(
        "operations.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasker_applications",
    )
    competency_areas = models.ManyToManyField(CompetencyArea, blank=True, related_name="applications")
    trust_score = models.FloatField(default=0.0)
    document_confidence = models.FloatField(default=0.0)
    competency_confidence = models.FloatField(default=0.0)
    interview_confidence = models.FloatField(default=0.0)
    fraud_risk_score = models.FloatField(default=0.0)
    manual_review_required = models.BooleanField(default=False)
    human_override = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_tasker_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.applicant.username} ({self.get_status_display()})"


class TaskerDocument(models.Model):
    class DocumentType(models.TextChoices):
        RESUME = "resume", "Resume / CV"
        CERTIFICATE = "certificate", "Certificate"
        CREDENTIAL = "credential", "Academic Credential"
        PORTFOLIO = "portfolio", "Portfolio Sample"
        GOVERNMENT_ID = "government_id", "Government ID"
        SELFIE = "selfie", "Selfie"
        OTHER = "other", "Other"

    application = models.ForeignKey(TaskerApplication, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file = models.FileField(
        upload_to="trust/taskers/%Y/%m/%d/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf",
                    "doc",
                    "docx",
                    "png",
                    "jpg",
                    "jpeg",
                    "webp",
                    "txt",
                ]
            )
        ],
    )
    description = models.TextField(blank=True, default="")
    extracted_text = models.TextField(blank=True, default="")
    authenticity_score = models.FloatField(default=0.0)
    risk_flags = models.JSONField(default=list, blank=True)
    sha256_hash = models.CharField(max_length=128, blank=True, default="")
    verified_by_ai = models.BooleanField(default=False)
    needs_manual_review = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.application.applicant.username}"


class IdentityVerification(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    application = models.OneToOneField(TaskerApplication, on_delete=models.CASCADE, related_name="identity_verification")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    selfie_image = models.ImageField(
        upload_to="trust/selfies/%Y/%m/%d/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])],
    )
    id_front_image = models.ImageField(
        upload_to="trust/ids/%Y/%m/%d/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    id_back_image = models.ImageField(
        upload_to="trust/ids/%Y/%m/%d/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp", "pdf"])],
    )
    face_match_score = models.FloatField(default=0.0)
    liveness_score = models.FloatField(default=0.0)
    document_match_score = models.FloatField(default=0.0)
    authenticity_score = models.FloatField(default=0.0)
    review_notes = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="identity_reviews")
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Identity check for {self.application.applicant.username}"


class AIInterviewSession(models.Model):
    class Mode(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        WRITING = "writing", "Writing"
        BEHAVIORAL = "behavioral", "Behavioral"
        BLENDED = "blended", "Blended"

    application = models.ForeignKey(TaskerApplication, on_delete=models.CASCADE, related_name="interview_sessions")
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.BLENDED)
    transcript = models.JSONField(default=list, blank=True)
    transcript_text = models.TextField(blank=True, default="")
    technical_score = models.FloatField(default=0.0)
    writing_score = models.FloatField(default=0.0)
    behavioral_score = models.FloatField(default=0.0)
    overall_score = models.FloatField(default=0.0)
    recommendation = models.CharField(max_length=60, blank=True, default="")
    ranking_percentile = models.FloatField(default=0.0)
    interviewer_version = models.CharField(max_length=60, blank=True, default="v1")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Interview for {self.application.applicant.username}"


class AIInterviewScore(models.Model):
    session = models.ForeignKey(AIInterviewSession, on_delete=models.CASCADE, related_name="scores")
    competency_area = models.ForeignKey(CompetencyArea, on_delete=models.CASCADE, related_name="interview_scores")
    score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    evidence = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("session", "competency_area")

    def __str__(self):
        return f"{self.competency_area.name}: {self.score}"

