from django.contrib import admin
from .models import UserActivity, MLPrediction


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'path', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['user__username', 'path']
    readonly_fields = ['user', 'action', 'path', 'metadata', 'timestamp']


@admin.register(MLPrediction)
class MLPredictionAdmin(admin.ModelAdmin):
    list_display = ['user', 'health_score', 'churn_probability', 'engagement_level', 'last_calculated']
    list_filter = ['engagement_level']
    readonly_fields = ['user', 'churn_probability', 'health_score', 'engagement_level',
                       'predicted_usage_next_month', 'recommendations', 'last_calculated']
