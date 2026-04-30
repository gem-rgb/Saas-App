from django.contrib import admin
from .models import TaskerProfile, Assignment, AssignmentFile, AssignmentAssignment, AssignmentSubmission


@admin.register(TaskerProfile)
class TaskerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'skill_level',
        'trust_score',
        'quality_score',
        'kyc_status',
        'competency_status',
        'interview_status',
        'approval_status',
        'is_active_tasker',
    )
    list_filter = ('skill_level', 'kyc_status', 'competency_status', 'interview_status', 'approval_status', 'is_active_tasker', 'created_at')
    search_fields = ('user__username', 'user__email', 'skills')
    readonly_fields = ('created_at', 'updated_at', 'last_assessed_at')


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'status', 'priority', 'assigned_to', 'deadline', 'ml_match_score')
    list_filter = ('status', 'priority', 'created_at', 'deadline')
    search_fields = ('title', 'description', 'creator__username')
    readonly_fields = ('created_at', 'updated_at', 'ml_match_score')
    fieldsets = (
        ('Basic Info', {
            'fields': ('creator', 'title', 'description', 'required_skills')
        }),
        ('Assignment Details', {
            'fields': ('status', 'priority', 'assigned_to', 'assigned_at', 'completed_at')
        }),
        ('Timeline', {
            'fields': ('deadline', 'estimated_hours')
        }),
        ('Budget & ML', {
            'fields': ('budget_cents', 'ml_match_score')
        }),
        ('Verification', {
            'fields': ('verification_rubric',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )


class AssignmentFileInline(admin.TabularInline):
    model = AssignmentFile
    extra = 1


@admin.register(AssignmentFile)
class AssignmentFileAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'file_type', 'file_size_mb', 'uploaded_by', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('assignment__title', 'description')
    readonly_fields = ('uploaded_at', 'file_size_mb')


@admin.register(AssignmentAssignment)
class AssignmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'tasker', 'ml_match_score', 'assigned_at')
    list_filter = ('assigned_at', 'ml_match_score')
    search_fields = ('assignment__title', 'tasker__user__username')


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'tasker', 'status', 'rating', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'submitted_at', 'rating')
    search_fields = ('assignment__title', 'tasker__user__username')
    readonly_fields = ('submitted_at', 'reviewed_at')
