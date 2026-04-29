from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('v1/me/', views.me_view, name='me'),
    path('v1/subscription/', views.subscription_view, name='subscription'),
    path('v1/analytics/health-score/', views.health_score_view, name='health-score'),
    path('v1/analytics/usage/', views.usage_view, name='usage'),
    path('v1/analytics/recommendations/', views.recommendations_view, name='recommendations'),
    path('v1/analytics/activity/', views.activity_view, name='activity'),
    path('v1/portal/summary/', views.portal_summary_view, name='portal-summary'),
    path('v1/marketplace/tasks/', views.marketplace_tasks_view, name='marketplace-tasks'),
    path('v1/trust/application/', views.trust_application_view, name='trust-application'),
    path('v1/operations/overview/', views.operations_overview_view, name='operations-overview'),
]
