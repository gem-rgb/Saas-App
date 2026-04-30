from django.contrib import admin

from marketplace.models import (
    TaskAttachment,
    TaskAuditEvent,
    TaskCategory,
    TaskConversationMessage,
    TaskConversationReadState,
    TaskMatchSuggestion,
    TaskNotification,
    TaskOrder,
    TaskPayment,
    TaskRating,
    TaskRevisionRequest,
    TaskStatusEvent,
    TaskSubmission,
)


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "order")
    list_filter = ("active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TaskOrder)
class TaskOrderAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "status", "complexity_level", "assigned_tasker", "deadline", "assignment_confidence")
    list_filter = ("status", "complexity_level", "payment_status", "created_at")
    search_fields = ("title", "subject", "student__username", "student__email")
    readonly_fields = ("published_at", "assigned_at", "completed_at", "cancelled_at", "created_at", "updated_at")


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ("task", "file_kind", "uploaded_by", "uploaded_at", "file_size_mb")
    list_filter = ("file_kind", "uploaded_at")
    search_fields = ("task__title", "description")
    readonly_fields = ("uploaded_at", "file_size_mb")


@admin.register(TaskMatchSuggestion)
class TaskMatchSuggestionAdmin(admin.ModelAdmin):
    list_display = ("task", "tasker", "score", "confidence", "ranking_position", "state", "is_primary")
    list_filter = ("state", "is_primary")
    search_fields = ("task__title", "tasker__user__username")


@admin.register(TaskStatusEvent)
class TaskStatusEventAdmin(admin.ModelAdmin):
    list_display = ("task", "previous_status", "new_status", "actor_role", "created_at")
    list_filter = ("new_status", "actor_role", "created_at")
    search_fields = ("task__title", "note")
    readonly_fields = ("created_at",)


@admin.register(TaskSubmission)
class TaskSubmissionAdmin(admin.ModelAdmin):
    list_display = ("task", "tasker", "status", "version", "quality_score", "submitted_at")
    list_filter = ("status", "submitted_at")
    search_fields = ("task__title", "tasker__user__username")
    readonly_fields = ("submitted_at", "reviewed_at")


@admin.register(TaskRevisionRequest)
class TaskRevisionRequestAdmin(admin.ModelAdmin):
    list_display = ("submission", "requested_by", "status", "due_at", "created_at")
    list_filter = ("status", "created_at")


@admin.register(TaskRating)
class TaskRatingAdmin(admin.ModelAdmin):
    list_display = ("task", "tasker", "client", "overall_rating", "created_at")
    list_filter = ("overall_rating", "created_at")


@admin.register(TaskPayment)
class TaskPaymentAdmin(admin.ModelAdmin):
    list_display = ("task", "amount_cents", "currency", "status", "escrow_status", "created_at")
    list_filter = ("status", "escrow_status", "currency")


@admin.register(TaskConversationMessage)
class TaskConversationMessageAdmin(admin.ModelAdmin):
    list_display = ("task", "sender", "is_ai", "channel", "created_at")
    list_filter = ("is_ai", "channel", "created_at")


@admin.register(TaskConversationReadState)
class TaskConversationReadStateAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "last_read_at", "updated_at")
    search_fields = ("task__title", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaskNotification)
class TaskNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "task", "channel", "title", "is_read", "created_at")
    list_filter = ("channel", "is_read", "created_at")


@admin.register(TaskAuditEvent)
class TaskAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "task", "actor_role", "created_at")
    list_filter = ("event_type", "actor_role", "created_at")
