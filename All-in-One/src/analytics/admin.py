from django.contrib import admin

from .models import MLPrediction, PlagiarismSnapshot, UserActivity


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ["user", "action", "path", "timestamp"]
    list_filter = ["action", "timestamp"]
    search_fields = ["user__username", "path"]
    readonly_fields = ["user", "action", "path", "metadata", "timestamp"]


@admin.register(MLPrediction)
class MLPredictionAdmin(admin.ModelAdmin):
    list_display = ["user", "health_score", "engagement_level", "last_calculated"]
    list_filter = ["engagement_level"]
    fields = [
        "user",
        "health_score",
        "engagement_level",
        "predicted_usage_next_month",
        "recommendations",
        "last_calculated",
    ]
    readonly_fields = [
        "user",
        "health_score",
        "engagement_level",
        "predicted_usage_next_month",
        "recommendations",
        "last_calculated",
    ]


@admin.register(PlagiarismSnapshot)
class PlagiarismSnapshotAdmin(admin.ModelAdmin):
    list_display = ["cache_key", "cache_type", "source_kind", "source_object_id", "author", "sample_text_count", "refreshed_at"]
    list_filter = ["cache_type", "source_kind", "refreshed_at"]
    search_fields = ["cache_key", "author__username"]
    readonly_fields = [
        "cache_key",
        "cache_type",
        "source_kind",
        "source_object_id",
        "author",
        "payload",
        "source_hash",
        "sample_text_count",
        "source_window_days",
        "refreshed_at",
    ]
