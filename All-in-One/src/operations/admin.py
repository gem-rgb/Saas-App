from django.contrib import admin

from operations.models import (
    EscalationCase,
    ManagerApplication,
    ManagerProfile,
    QualityAudit,
    Region,
    RegionalAssignment,
    TaskerPerformanceSnapshot,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "timezone", "active", "staff_target")
    list_filter = ("active", "timezone")
    search_fields = ("name", "code")


@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "active", "escalation_limit")
    list_filter = ("active",)
    search_fields = ("user__username", "user__email", "title")
    filter_horizontal = ("regions",)


@admin.register(ManagerApplication)
class ManagerApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "title", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email", "title", "bio")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    filter_horizontal = ("regions",)


@admin.register(RegionalAssignment)
class RegionalAssignmentAdmin(admin.ModelAdmin):
    list_display = ("tasker", "region", "manager", "active", "assigned_at")
    list_filter = ("active", "region")
    search_fields = ("tasker__user__username", "region__name")


@admin.register(EscalationCase)
class EscalationCaseAdmin(admin.ModelAdmin):
    list_display = ("task", "region", "status", "priority", "assigned_manager", "opened_at")
    list_filter = ("status", "priority", "region")
    search_fields = ("task__title", "reason")


@admin.register(QualityAudit)
class QualityAuditAdmin(admin.ModelAdmin):
    list_display = ("task", "manager", "audit_score", "outcome", "created_at")
    list_filter = ("outcome", "created_at")


@admin.register(TaskerPerformanceSnapshot)
class TaskerPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("tasker", "region", "ranking_score", "quality_rating", "on_time_rate", "fraud_risk_score", "period_end")
    list_filter = ("region", "period_end")
    search_fields = ("tasker__user__username",)
