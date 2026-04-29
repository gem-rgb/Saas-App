from django.contrib import admin

from trust.models import AIInterviewScore, AIInterviewSession, CompetencyArea, IdentityVerification, TaskerApplication, TaskerDocument


@admin.register(CompetencyArea)
class CompetencyAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "order")
    list_filter = ("active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TaskerApplication)
class TaskerApplicationAdmin(admin.ModelAdmin):
    list_display = ("applicant", "status", "trust_score", "document_confidence", "competency_confidence", "interview_confidence", "manual_review_required")
    list_filter = ("status", "manual_review_required", "created_at")
    search_fields = ("applicant__username", "applicant__email", "headline", "bio")
    readonly_fields = ("trust_score", "document_confidence", "competency_confidence", "interview_confidence", "fraud_risk_score", "created_at", "updated_at")
    filter_horizontal = ("competency_areas",)


@admin.register(TaskerDocument)
class TaskerDocumentAdmin(admin.ModelAdmin):
    list_display = ("application", "document_type", "authenticity_score", "verified_by_ai", "needs_manual_review", "uploaded_at")
    list_filter = ("document_type", "verified_by_ai", "needs_manual_review")
    search_fields = ("application__applicant__username", "description")
    readonly_fields = ("uploaded_at",)


@admin.register(IdentityVerification)
class IdentityVerificationAdmin(admin.ModelAdmin):
    list_display = ("application", "status", "face_match_score", "liveness_score", "document_match_score", "authenticity_score", "verified_at")
    list_filter = ("status", "verified_at")
    readonly_fields = ("verified_at",)


@admin.register(AIInterviewSession)
class AIInterviewSessionAdmin(admin.ModelAdmin):
    list_display = ("application", "mode", "overall_score", "recommendation", "started_at", "ended_at")
    list_filter = ("mode", "started_at")
    readonly_fields = ("started_at", "ended_at")


@admin.register(AIInterviewScore)
class AIInterviewScoreAdmin(admin.ModelAdmin):
    list_display = ("session", "competency_area", "score", "created_at")
    list_filter = ("competency_area",)

